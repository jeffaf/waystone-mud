"""Simulated Players System for Waystone MUD.

Provides infrastructure for simulated player characters that can execute
commands and interact with the game world without a real telnet connection.

Phase 1 Implementation - Core Infrastructure:
- SimulatedPlayerManager: Central coordinator for simulated players
- SimulatedCommandContext: Fake context that captures output to buffer
- SimulatedSession: Lightweight session for simulated players
- SimulatedConnection: Captures output instead of sending to network
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import structlog

from waystone.network import SessionState

if TYPE_CHECKING:
    from waystone.game.engine import GameEngine

logger = structlog.get_logger(__name__)


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

    This is a skeleton implementation for Phase 1 - actual behavior
    logic will be added in later phases.
    """

    def __init__(self) -> None:
        """Initialize the simulated player manager."""
        self.active_sims: dict[str, object] = {}  # sim_id -> SimulatedPlayer (future)
        self.enabled: bool = True

        logger.info("simulated_player_manager_initialized")

    def get_active(self) -> list[object]:
        """
        Return list of active simulated players.

        Returns:
            List of active SimulatedPlayer instances (empty in Phase 1)
        """
        return list(self.active_sims.values())

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

        # Phase 1: No actual behavior yet - just a skeleton
        # Future phases will iterate over active_sims and call their tick methods
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
