"""Simulated Players System for Waystone MUD.

Provides infrastructure for simulated player characters that can execute
commands and interact with the game world without a real telnet connection.

Phase 1 Implementation - Core Infrastructure:
- SimulatedPlayerManager: Central coordinator for simulated players
- SimulatedCommandContext: Fake context that captures output to buffer
- SimulatedSession: Lightweight session for simulated players
- SimulatedConnection: Captures output instead of sending to network

Phase 2 Implementation - Lifecycle Management:
- BartleType: Enum for player personality types
- SimulatedPlayerConfig: Configuration for simulated players
- SimulatedPlayer: Runtime instance of a simulated player
- Login/Logout mechanics with database integration
- Room presence and who list integration

Phase 3 Implementation - Movement (Explorer MVP):
- BehaviorStatus/BehaviorResult/BehaviorAction: Behavior tree primitives
- BehaviorNode: Abstract base for behavior nodes
- SimMemory: Short-term memory for tracking visited rooms/directions
- ExplorerBehavior: Movement behavior for Explorer personality
- Command execution through SimulatedCommandContext
- tick() with behavior execution
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import structlog

from waystone.database.models import Character, CharacterBackground
from waystone.network import SessionState

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from waystone.game.engine import GameEngine
    from waystone.game.world import Room

logger = structlog.get_logger(__name__)


# =============================================================================
# Phase 3: Behavior Tree Framework
# =============================================================================


class BehaviorStatus(str, Enum):
    """Status returned by behavior nodes."""

    SUCCESS = "success"
    FAILURE = "failure"
    RUNNING = "running"


@dataclass
class BehaviorAction:
    """An action to be executed by a simulated player."""

    command: str  # The command to execute (e.g., "north", "look")
    args: list[str] = field(default_factory=list)  # Arguments for the command


@dataclass
class BehaviorResult:
    """Result from evaluating a behavior node."""

    status: BehaviorStatus
    action: BehaviorAction | None = None


class BehaviorNode(ABC):
    """
    Abstract base class for behavior tree nodes.

    Each node can check a condition and execute to produce a result.
    """

    @abstractmethod
    def condition(self, context: Any) -> bool:
        """
        Check if this node should execute.

        Args:
            context: Context information for the check

        Returns:
            True if the node should execute
        """
        raise NotImplementedError

    @abstractmethod
    def execute(self, context: Any) -> BehaviorResult:
        """
        Execute this node's behavior.

        Args:
            context: Context information for execution

        Returns:
            BehaviorResult with status and optional action
        """
        raise NotImplementedError


# =============================================================================
# Phase 3: SimMemory - Short-term memory for simulated players
# =============================================================================


@dataclass
class SimMemory:
    """
    Short-term memory for a simulated player.

    Tracks recently visited rooms and directions to inform
    behavior decisions like avoiding backtracking.
    """

    # Directions we've gone from the current room
    visited_directions: set[str] = field(default_factory=set)

    # Last direction we moved
    last_direction: str | None = None

    # Recent room IDs (limited history)
    recent_rooms: deque[str] = field(default_factory=lambda: deque(maxlen=10))

    # Current room ID
    current_room_id: str | None = None

    def add_room(self, room_id: str) -> None:
        """
        Add a room to the recent history.

        Args:
            room_id: The room ID to record
        """
        if room_id not in self.recent_rooms:
            self.recent_rooms.append(room_id)

    def clear_visited_directions(self) -> None:
        """Clear visited directions when entering a new room."""
        self.visited_directions.clear()


# =============================================================================
# Phase 3: ExplorerBehavior - Movement behavior for Explorer personality
# =============================================================================


class ExplorerBehavior:
    """
    Behavior implementation for Explorer personality type.

    Explorers primarily want to move around and discover new areas.
    They prefer unexplored exits, avoid immediate backtracking,
    and occasionally look around or check exits.

    Weighted action selection:
    - 80% move to an exit
    - 15% look at current room
    - 5% check exits
    """

    # Direction opposites for backtrack detection
    OPPOSITES = {
        "north": "south",
        "south": "north",
        "east": "west",
        "west": "east",
        "up": "down",
        "down": "up",
        "northeast": "southwest",
        "southwest": "northeast",
        "northwest": "southeast",
        "southeast": "northwest",
        "in": "out",
        "out": "in",
    }

    def select_action(
        self,
        available_exits: list[str],
        memory: SimMemory,
        last_direction: str | None,
    ) -> BehaviorAction:
        """
        Select the next action for the Explorer.

        Uses weighted randomness:
        - 80% chance to move (if exits available)
        - 15% chance to look
        - 5% chance to check exits

        Args:
            available_exits: List of valid exit directions
            memory: The player's short-term memory
            last_direction: The direction we last moved (to avoid backtracking)

        Returns:
            BehaviorAction to execute
        """
        # Weight-based selection
        roll = random.random()

        # 5% check exits
        if roll < 0.05:
            return BehaviorAction(command="exits", args=[])

        # 15% look
        if roll < 0.20:
            return BehaviorAction(command="look", args=[])

        # 80% move (if exits available)
        if available_exits:
            direction = self._choose_direction(available_exits, memory, last_direction)
            return BehaviorAction(command=direction, args=[])

        # No exits - look instead
        return BehaviorAction(command="look", args=[])

    def _choose_direction(
        self,
        available_exits: list[str],
        memory: SimMemory,
        last_direction: str | None,
    ) -> str:
        """
        Choose a direction to move, avoiding backtracking when possible.

        Priorities:
        1. Unvisited exits (not in memory.visited_directions)
        2. Any exit that's not backtracking
        3. Backtrack (only if no other option)

        Args:
            available_exits: List of valid exit directions
            memory: The player's short-term memory
            last_direction: The direction we last moved

        Returns:
            Direction to move
        """
        if not available_exits:
            raise ValueError("No available exits")

        # Identify backtrack direction
        backtrack_direction = None
        if last_direction:
            backtrack_direction = self._get_opposite_direction(last_direction)

        # Categorize exits
        unvisited = []
        non_backtrack = []
        backtrack = []

        for exit_dir in available_exits:
            if exit_dir not in memory.visited_directions:
                unvisited.append(exit_dir)

            if exit_dir == backtrack_direction:
                backtrack.append(exit_dir)
            else:
                non_backtrack.append(exit_dir)

        # Preference order: unvisited non-backtrack > non-backtrack > backtrack
        unvisited_non_backtrack = [d for d in unvisited if d in non_backtrack]
        if unvisited_non_backtrack:
            return random.choice(unvisited_non_backtrack)

        if non_backtrack:
            return random.choice(non_backtrack)

        # Only backtracking available
        return random.choice(available_exits)

    def _get_opposite_direction(self, direction: str) -> str | None:
        """
        Get the opposite direction for backtrack detection.

        Args:
            direction: The direction to get opposite of

        Returns:
            Opposite direction, or None if unknown
        """
        return self.OPPOSITES.get(direction.lower())


# =============================================================================
# BartleType - Player personality classification
# =============================================================================


class BartleType(str, Enum):
    """
    Bartle player type classification.

    Defines the four primary player types from Bartle's taxonomy:
    - ACHIEVER: Focused on progress, levels, and completion
    - EXPLORER: Focused on discovery, secrets, and understanding
    - SOCIALIZER: Focused on connection, conversation, and community
    - KILLER: Focused on competition, dominance, and PvP
    """

    ACHIEVER = "achiever"
    EXPLORER = "explorer"
    SOCIALIZER = "socializer"
    KILLER = "killer"


# =============================================================================
# SimulatedPlayerConfig - Configuration for simulated players
# =============================================================================


@dataclass
class SimulatedPlayerConfig:
    """
    Configuration for a simulated player personality.

    Defines the identity, Bartle type, and schedule for a simulated player.
    This is the static configuration that gets loaded from YAML or database.
    """

    id: str  # Unique ID (e.g., "sim_explorer_lyra")
    name: str  # Character name (e.g., "Lyra")
    background: CharacterBackground  # Character background
    bartle_type: BartleType  # Personality type

    # Schedule configuration
    active_hours: tuple[int, int] = (8, 22)  # Start and end hour (24h format)
    session_duration_minutes: tuple[int, int] = (60, 240)  # Min and max session length

    # Starting location
    starting_room: str = "university_main_gates"

    # Personality traits (0.0 to 1.0)
    chattiness: float = 0.5
    helpfulness: float = 0.5
    aggression: float = 0.5
    curiosity: float = 0.5


# =============================================================================
# SimulatedPlayer - Runtime instance of a simulated player
# =============================================================================


@dataclass
class SimulatedPlayer:
    """
    Active simulated player instance.

    Wraps a configuration and character ID, tracking runtime state
    like the current session and login status.
    """

    config: SimulatedPlayerConfig
    character_id: str  # Database character UUID as string

    # Session state
    session: SimulatedSession | None = None
    logged_in_at: datetime | None = None
    will_logout_at: datetime | None = None

    # Phase 3: Behavior and memory
    behavior: ExplorerBehavior | None = None
    memory: SimMemory = field(default_factory=SimMemory)

    @property
    def is_logged_in(self) -> bool:
        """Check if the simulated player is currently logged in."""
        return self.session is not None


# =============================================================================
# SimulatedConnection - Captures output instead of sending to network
# =============================================================================


class SimulatedConnection:
    """
    A fake connection that captures output to a buffer.

    Used by simulated players to execute commands without a real
    network connection. All output is stored in output_buffer for
    later inspection or logging.
    """

    def __init__(self) -> None:
        """Initialize a new simulated connection."""
        self.id: UUID = uuid4()
        self.output_buffer: list[str] = []
        self._closed = False
        self.ip_address = "simulated"

        logger.debug(
            "simulated_connection_created",
            connection_id=str(self.id),
        )

    async def send(self, message: str) -> None:
        """
        Capture a message to the output buffer.

        Args:
            message: Text to capture
        """
        if not self._closed:
            self.output_buffer.append(message)

    async def send_line(self, message: str) -> None:
        """
        Capture a message to the output buffer.

        Args:
            message: Text to capture (newline not added, just captured as-is)
        """
        if not self._closed:
            self.output_buffer.append(message)

    def clear_buffer(self) -> None:
        """Clear the output buffer."""
        self.output_buffer = []

    def close(self) -> None:
        """Mark the connection as closed."""
        self._closed = True
        logger.debug(
            "simulated_connection_closed",
            connection_id=str(self.id),
        )

    @property
    def is_closed(self) -> bool:
        """Check if connection is closed."""
        return self._closed

    def __repr__(self) -> str:
        """Detailed representation of connection."""
        return f"SimulatedConnection(id={self.id}, closed={self._closed})"


# =============================================================================
# SimulatedSession - Lightweight session for simulated players
# =============================================================================


@dataclass
class SimulatedSession:
    """
    A lightweight session for simulated player characters.

    Satisfies the Session interface expected by commands but does not
    require a real network connection. Always in PLAYING state.
    """

    character_id: str
    id: UUID = field(default_factory=uuid4)
    user_id: str | None = None
    state: SessionState = SessionState.PLAYING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_activity: datetime = field(default_factory=lambda: datetime.now(UTC))
    data: dict[str, object] = field(default_factory=dict)
    _connection: SimulatedConnection | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Initialize connection after dataclass creation."""
        if self._connection is None:
            self._connection = SimulatedConnection()

    @property
    def connection(self) -> SimulatedConnection:
        """Get the simulated connection."""
        if self._connection is None:
            self._connection = SimulatedConnection()
        return self._connection

    @property
    def is_simulated(self) -> bool:
        """Identify this as a simulated session."""
        return True

    def update_activity(self) -> None:
        """Update the last activity timestamp."""
        self.last_activity = datetime.now(UTC)

    def __repr__(self) -> str:
        """String representation of session."""
        return f"SimulatedSession(id={self.id}, character_id={self.character_id})"


# =============================================================================
# SimulatedCommandContext - Context for executing commands
# =============================================================================


@dataclass
class SimulatedCommandContext:
    """
    Command context for simulated players.

    Mirrors the CommandContext interface from waystone.game.commands.base
    but uses a SimulatedSession and SimulatedConnection to capture output
    instead of sending to a real client.
    """

    session: SimulatedSession
    engine: GameEngine | None
    args: list[str]
    raw_input: str

    @property
    def connection(self) -> SimulatedConnection:
        """Get the simulated connection from session."""
        return self.session.connection


# =============================================================================
# SimulatedPlayerManager - Central coordinator
# =============================================================================


class SimulatedPlayerManager:
    """
    Manages simulated player lifecycle and ticks.

    Coordinates all simulated players in the game, handling their
    login/logout schedules and dispatching tick updates for behavior.

    Phase 2 adds:
    - Config management for simulated player definitions
    - Login/logout mechanics with database integration
    - Active hour scheduling
    """

    def __init__(self) -> None:
        """Initialize the simulated player manager."""
        self.active_sims: dict[str, SimulatedPlayer] = {}  # sim_id -> SimulatedPlayer
        self.configs: dict[str, SimulatedPlayerConfig] = {}  # sim_id -> Config
        self.enabled: bool = True

        logger.info("simulated_player_manager_initialized")

    def add_config(self, config: SimulatedPlayerConfig) -> None:
        """
        Register a simulated player configuration.

        Args:
            config: The configuration to register
        """
        self.configs[config.id] = config
        logger.debug(
            "simulated_player_config_added",
            sim_id=config.id,
            name=config.name,
            bartle_type=config.bartle_type.value,
        )

    def get_config(self, sim_id: str) -> SimulatedPlayerConfig | None:
        """
        Get a simulated player configuration by ID.

        Args:
            sim_id: The config ID to look up

        Returns:
            The configuration if found, None otherwise
        """
        return self.configs.get(sim_id)

    def get_active(self) -> list[SimulatedPlayer]:
        """
        Return list of active simulated players.

        Returns:
            List of active SimulatedPlayer instances
        """
        return list(self.active_sims.values())

    async def login_player(
        self,
        sim_id: str,
        db_session: AsyncSession,
        room: Room | None = None,
    ) -> SimulatedPlayer | None:
        """
        Log in a simulated player, creating Character if needed.

        Creates a Character record in the database if one doesn't exist,
        then creates a SimulatedSession and adds the player to the room.

        Args:
            sim_id: The config ID of the player to log in
            db_session: Database session for character operations
            room: Optional room to place the player in

        Returns:
            The SimulatedPlayer instance if successful, None otherwise
        """
        config = self.configs.get(sim_id)
        if config is None:
            logger.warning(
                "simulated_player_login_failed_no_config",
                sim_id=sim_id,
            )
            return None

        # Check if already logged in
        if sim_id in self.active_sims:
            logger.debug(
                "simulated_player_already_logged_in",
                sim_id=sim_id,
            )
            return self.active_sims[sim_id]

        # Get or create Character in database
        character = await self._get_or_create_character(config, db_session)

        # Create SimulatedPlayer instance
        sim_player = SimulatedPlayer(
            config=config,
            character_id=str(character.id),
        )

        # Create session and mark as logged in
        session = SimulatedSession(character_id=str(character.id))
        sim_player.session = session
        sim_player.logged_in_at = datetime.now(UTC)

        # Add to active sims
        self.active_sims[sim_id] = sim_player

        # Add to room if provided
        if room is not None:
            room.add_player(str(character.id))
            logger.debug(
                "simulated_player_added_to_room",
                sim_id=sim_id,
                room_id=room.id,
            )

        logger.info(
            "simulated_player_logged_in",
            sim_id=sim_id,
            character_name=config.name,
            character_id=str(character.id),
        )

        return sim_player

    async def logout_player(
        self,
        sim_id: str,
        room: Room | None = None,
    ) -> bool:
        """
        Log out a simulated player.

        Removes the player from active_sims and cleans up session state.

        Args:
            sim_id: The config ID of the player to log out
            room: Optional room to remove the player from

        Returns:
            True if logout succeeded, False if player not found
        """
        sim_player = self.active_sims.get(sim_id)
        if sim_player is None:
            logger.warning(
                "simulated_player_logout_failed_not_active",
                sim_id=sim_id,
            )
            return False

        # Remove from room if provided
        if room is not None:
            room.remove_player(sim_player.character_id)
            logger.debug(
                "simulated_player_removed_from_room",
                sim_id=sim_id,
                room_id=room.id,
            )

        # Clean up session
        if sim_player.session is not None:
            sim_player.session.connection.close()
        sim_player.session = None
        sim_player.logged_in_at = None

        # Remove from active sims
        del self.active_sims[sim_id]

        logger.info(
            "simulated_player_logged_out",
            sim_id=sim_id,
            character_name=sim_player.config.name,
        )

        return True

    async def _get_or_create_character(
        self,
        config: SimulatedPlayerConfig,
        db_session: AsyncSession,
    ) -> Character:
        """
        Get existing or create new Character for simulated player.

        Args:
            config: The simulated player configuration
            db_session: Database session

        Returns:
            The Character instance
        """
        from sqlalchemy import select

        from waystone.database.models import Character, User

        # Look for existing character by name
        result = await db_session.execute(select(Character).where(Character.name == config.name))
        character = result.scalar_one_or_none()

        if character is not None:
            # Update room if character exists
            character.current_room_id = config.starting_room
            await db_session.commit()
            return character

        # Need to create a simulated user first (or use a shared system user)
        user_result = await db_session.execute(
            select(User).where(User.username == "system_simulated")
        )
        system_user = user_result.scalar_one_or_none()

        if system_user is None:
            # Create system user for simulated players
            system_user = User(
                username="system_simulated",
                email="simulated@waystone.local",
                password_hash=User.hash_password(str(uuid4())),  # Random password
            )
            db_session.add(system_user)
            await db_session.commit()
            await db_session.refresh(system_user)

        # Create the character (system_user is guaranteed to exist here)
        character = Character(
            user_id=system_user.id,
            name=config.name,
            background=config.background,
            current_room_id=config.starting_room,
            is_simulated=True,
        )
        db_session.add(character)
        await db_session.commit()
        await db_session.refresh(character)

        logger.info(
            "simulated_player_character_created",
            character_id=str(character.id),
            name=config.name,
        )

        return character

    def _is_active_hour(self, config: SimulatedPlayerConfig, hour: int) -> bool:
        """
        Check if the given hour is within the config's active hours.

        Handles wrap-around for night owl schedules (e.g., 22:00 to 06:00).

        Args:
            config: The player configuration
            hour: Hour to check (0-23)

        Returns:
            True if the hour is within active hours
        """
        start_hour, end_hour = config.active_hours

        if start_hour <= end_hour:
            # Normal range (e.g., 8 to 22)
            return start_hour <= hour < end_hour
        else:
            # Wraps around midnight (e.g., 22 to 6)
            return hour >= start_hour or hour < end_hour

    async def execute_command(
        self,
        sim_player: SimulatedPlayer,
        command_str: str,
        engine: GameEngine | None = None,
    ) -> str:
        """
        Execute a command for a simulated player.

        Uses the command registry to find and execute the command,
        capturing output in the connection buffer.

        Args:
            sim_player: The simulated player executing the command
            command_str: The command string to execute
            engine: The game engine (for world access)

        Returns:
            The captured output as a string
        """
        if sim_player.session is None:
            logger.warning(
                "simulated_player_execute_no_session",
                character_id=sim_player.character_id,
                command=command_str,
            )
            return ""

        # Parse command and args
        parts = command_str.strip().split()
        if not parts:
            return ""

        cmd_name = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []

        # Get command from registry
        from waystone.game.commands.base import get_registry

        registry = get_registry()
        command = registry.get(cmd_name)

        if command is None:
            logger.debug(
                "simulated_player_unknown_command",
                character_id=sim_player.character_id,
                command=cmd_name,
            )
            return ""

        # Clear buffer before execution
        sim_player.session.connection.clear_buffer()

        # Create context and execute
        # Note: SimulatedCommandContext is duck-typed to be compatible with CommandContext
        ctx = SimulatedCommandContext(
            session=sim_player.session,
            engine=engine,
            args=args,
            raw_input=command_str,
        )

        try:
            await command.execute(ctx)  # type: ignore[arg-type]
        except Exception as e:
            logger.error(
                "simulated_player_command_error",
                character_id=sim_player.character_id,
                command=cmd_name,
                error=str(e),
            )

        # Return captured output
        return "\n".join(sim_player.session.connection.output_buffer)

    async def tick(self, engine: GameEngine | None) -> int:
        """
        Process a tick for all active simulated players.

        Called from the game engine's periodic cleanup loop.
        Runs behavior trees and executes selected actions.

        Args:
            engine: The game engine instance

        Returns:
            Number of actions taken this tick
        """
        if not self.enabled:
            return 0

        actions_taken = 0

        for sim_id, sim_player in self.active_sims.items():
            if not sim_player.is_logged_in:
                continue

            # Ensure behavior is set for Explorer types
            if sim_player.behavior is None:
                if sim_player.config.bartle_type == BartleType.EXPLORER:
                    sim_player.behavior = ExplorerBehavior()
                else:
                    # Skip non-Explorer types for now (Phase 3 is Explorer MVP)
                    continue

            if sim_player.behavior is None:
                continue

            # Get current room and available exits
            if engine is None or not hasattr(engine, "world"):
                continue

            # Get character's current room from database
            from sqlalchemy import select

            from waystone.database.engine import get_session as get_db_session
            from waystone.database.models import Character

            try:
                async with get_db_session() as db_session:
                    result = await db_session.execute(
                        select(Character).where(Character.id == UUID(sim_player.character_id))
                    )
                    character = result.scalar_one_or_none()

                    if character is None:
                        continue

                    room = engine.world.get(character.current_room_id)
                    if room is None:
                        continue

                    # Get available exits
                    available_exits = list(room.exits.keys())

                    # Select action using behavior
                    action = sim_player.behavior.select_action(
                        available_exits=available_exits,
                        memory=sim_player.memory,
                        last_direction=sim_player.memory.last_direction,
                    )

                    # Execute the action
                    command_str = action.command
                    if action.args:
                        command_str += " " + " ".join(action.args)

                    await self.execute_command(sim_player, command_str, engine)

                    # Update memory if we moved
                    if action.command in available_exits:
                        sim_player.memory.last_direction = action.command
                        sim_player.memory.visited_directions.add(action.command)

                    actions_taken += 1

                    logger.debug(
                        "simulated_player_action",
                        sim_id=sim_id,
                        character_name=sim_player.config.name,
                        action=command_str,
                    )

            except Exception as e:
                logger.error(
                    "simulated_player_tick_error",
                    sim_id=sim_id,
                    error=str(e),
                )

        if actions_taken > 0:
            logger.debug(
                "simulated_player_tick",
                actions=actions_taken,
                active_sims=len(self.active_sims),
            )

        return actions_taken


# =============================================================================
# Module-level singleton
# =============================================================================


_sim_manager: SimulatedPlayerManager | None = None


def get_sim_manager() -> SimulatedPlayerManager:
    """
    Get the global SimulatedPlayerManager singleton.

    Returns:
        The global SimulatedPlayerManager instance
    """
    global _sim_manager
    if _sim_manager is None:
        _sim_manager = SimulatedPlayerManager()
    return _sim_manager


def reset_sim_manager() -> None:
    """
    Reset the global SimulatedPlayerManager singleton.

    Used primarily for testing to ensure a fresh manager instance.
    """
    global _sim_manager
    _sim_manager = None
