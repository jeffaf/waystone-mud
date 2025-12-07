"""Session management for Waystone MUD connections."""

from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import structlog

from waystone.config import get_settings

if TYPE_CHECKING:
    from waystone.network.connection import Connection

logger = structlog.get_logger(__name__)


class SessionState(str, Enum):
    """Session state enumeration."""

    CONNECTED = "connected"  # Just connected, no auth yet
    AUTHENTICATING = "authenticating"  # In login/registration flow
    PLAYING = "playing"  # Authenticated and playing
    DISCONNECTED = "disconnected"  # Disconnected


class Session:
    """
    Represents a user session with authentication and state.

    Sessions track the connection state, user identity, and character
    context for a connected client.
    """

    def __init__(self, connection: "Connection") -> None:
        """
        Initialize a new session.

        Args:
            connection: The connection this session is bound to
        """
        self.id: UUID = uuid4()
        self.connection = connection
        self.user_id: str | None = None
        self.character_id: str | None = None
        self.state = SessionState.CONNECTED
        self.created_at = datetime.now(UTC)
        self.last_activity = datetime.now(UTC)

        logger.info(
            "session_created",
            session_id=str(self.id),
            connection_id=str(connection.id),
            ip_address=connection.ip_address,
        )

    def update_activity(self) -> None:
        """Update the last activity timestamp."""
        self.last_activity = datetime.now(UTC)

    def is_expired(self, timeout_minutes: int) -> bool:
        """
        Check if session has expired based on inactivity.

        Args:
            timeout_minutes: Number of minutes before expiration

        Returns:
            True if session is expired
        """
        timeout = timedelta(minutes=timeout_minutes)
        return datetime.now(UTC) - self.last_activity > timeout

    def set_user(self, user_id: str) -> None:
        """
        Set the authenticated user for this session.

        Args:
            user_id: The user ID
        """
        self.user_id = user_id
        self.update_activity()
        logger.info(
            "session_user_set",
            session_id=str(self.id),
            user_id=user_id,
        )

    def set_character(self, character_id: str) -> None:
        """
        Set the active character for this session.

        Args:
            character_id: The character ID
        """
        self.character_id = character_id
        self.update_activity()
        logger.info(
            "session_character_set",
            session_id=str(self.id),
            character_id=character_id,
        )

    def set_state(self, state: SessionState) -> None:
        """
        Update session state.

        Args:
            state: New session state
        """
        old_state = self.state
        self.state = state
        self.update_activity()
        logger.info(
            "session_state_changed",
            session_id=str(self.id),
            old_state=old_state.value,
            new_state=state.value,
        )

    def __str__(self) -> str:
        """String representation of session."""
        return f"Session({self.id}, {self.state.value})"

    def __repr__(self) -> str:
        """Detailed representation of session."""
        return (
            f"Session(id={self.id}, user_id={self.user_id}, "
            f"character_id={self.character_id}, state={self.state.value})"
        )


class SessionManager:
    """
    Manages all active sessions in memory.

    Provides session lifecycle management including creation, retrieval,
    destruction, and cleanup of expired sessions.
    """

    def __init__(self) -> None:
        """Initialize the session manager with in-memory storage."""
        self._sessions: dict[UUID, Session] = {}
        self._settings = get_settings()
        logger.info("session_manager_initialized")

    def create_session(self, connection: "Connection") -> Session:
        """
        Create a new session for a connection.

        Args:
            connection: The connection to create a session for

        Returns:
            The newly created session
        """
        session = Session(connection)
        self._sessions[session.id] = session

        # Link session to connection
        connection.session = session

        logger.info(
            "session_created_by_manager",
            session_id=str(session.id),
            connection_id=str(connection.id),
            total_sessions=len(self._sessions),
        )

        return session

    def get_session(self, session_id: UUID) -> Session | None:
        """
        Retrieve a session by ID.

        Args:
            session_id: The session ID to look up

        Returns:
            The session if found, None otherwise
        """
        return self._sessions.get(session_id)

    def get_session_by_user(self, user_id: str) -> Session | None:
        """
        Find a session by user ID.

        Args:
            user_id: The user ID to search for

        Returns:
            The first session found for the user, or None
        """
        for session in self._sessions.values():
            if session.user_id == user_id:
                return session
        return None

    def destroy_session(self, session_id: UUID) -> bool:
        """
        Destroy a session and remove it from tracking.

        Args:
            session_id: The session ID to destroy

        Returns:
            True if session was destroyed, False if not found
        """
        session = self._sessions.pop(session_id, None)
        if session:
            session.set_state(SessionState.DISCONNECTED)
            logger.info(
                "session_destroyed",
                session_id=str(session_id),
                total_sessions=len(self._sessions),
            )
            return True
        return False

    def update_activity(self, session_id: UUID) -> None:
        """
        Update the last activity time for a session.

        Args:
            session_id: The session ID to update
        """
        session = self.get_session(session_id)
        if session:
            session.update_activity()

    def cleanup_expired(self) -> int:
        """
        Remove expired sessions based on timeout configuration.

        Returns:
            Number of sessions removed
        """
        timeout_minutes = self._settings.session_timeout_minutes
        expired_ids: list[UUID] = []

        for session_id, session in self._sessions.items():
            if session.is_expired(timeout_minutes):
                expired_ids.append(session_id)

        for session_id in expired_ids:
            self.destroy_session(session_id)

        if expired_ids:
            logger.info(
                "sessions_expired",
                count=len(expired_ids),
                timeout_minutes=timeout_minutes,
            )

        return len(expired_ids)

    def get_all_sessions(self) -> list[Session]:
        """
        Get all active sessions.

        Returns:
            List of all sessions
        """
        return list(self._sessions.values())

    def get_session_count(self) -> int:
        """
        Get the total number of active sessions.

        Returns:
            Session count
        """
        return len(self._sessions)

    def __len__(self) -> int:
        """Return the number of active sessions."""
        return len(self._sessions)
