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
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING
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
        result = await db_session.execute(
            select(Character).where(Character.name == config.name)
        )
        character = result.scalar_one_or_none()

        if character is not None:
            # Update room if character exists
            character.current_room_id = config.starting_room
            await db_session.commit()
            return character

        # Need to create a simulated user first (or use a shared system user)
        result = await db_session.execute(
            select(User).where(User.username == "system_simulated")
        )
        system_user = result.scalar_one_or_none()

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

        # Create the character
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

    async def tick(self, engine: GameEngine | None) -> int:
        """
        Process a tick for all active simulated players.

        Called from the game engine's periodic cleanup loop.

        Args:
            engine: The game engine instance

        Returns:
            Number of actions taken this tick
        """
        if not self.enabled:
            return 0

        # Phase 2: Track actions but don't do behavior yet
        actions_taken = 0

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
