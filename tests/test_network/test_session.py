"""Tests for session management."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock
from uuid import UUID

import pytest

from waystone.network.connection import Connection
from waystone.network.session import Session, SessionManager, SessionState


class TestSession:
    """Test cases for Session class."""

    def test_session_creation(self) -> None:
        """Test creating a new session."""
        # Create a mock connection
        mock_connection = Mock(spec=Connection)
        mock_connection.id = UUID("12345678-1234-5678-1234-567812345678")
        mock_connection.ip_address = "127.0.0.1"

        # Create session
        session = Session(mock_connection)

        # Verify session initialization
        assert isinstance(session.id, UUID)
        assert session.connection == mock_connection
        assert session.user_id is None
        assert session.character_id is None
        assert session.state == SessionState.CONNECTED
        assert isinstance(session.created_at, datetime)
        assert isinstance(session.last_activity, datetime)

    def test_update_activity(self) -> None:
        """Test updating session activity timestamp."""
        mock_connection = Mock(spec=Connection)
        mock_connection.id = UUID("12345678-1234-5678-1234-567812345678")
        mock_connection.ip_address = "127.0.0.1"
        session = Session(mock_connection)

        # Get initial timestamp
        initial_activity = session.last_activity

        # Wait a bit and update
        import time

        time.sleep(0.01)
        session.update_activity()

        # Verify timestamp updated
        assert session.last_activity > initial_activity

    def test_is_expired(self) -> None:
        """Test session expiration check."""
        mock_connection = Mock(spec=Connection)
        mock_connection.id = UUID("12345678-1234-5678-1234-567812345678")
        mock_connection.ip_address = "127.0.0.1"
        session = Session(mock_connection)

        # Session should not be expired immediately
        assert not session.is_expired(60)

        # Manually set last_activity to past
        session.last_activity = datetime.now(timezone.utc) - timedelta(minutes=61)

        # Session should now be expired
        assert session.is_expired(60)

    def test_set_user(self) -> None:
        """Test setting user ID on session."""
        mock_connection = Mock(spec=Connection)
        mock_connection.id = UUID("12345678-1234-5678-1234-567812345678")
        mock_connection.ip_address = "127.0.0.1"
        session = Session(mock_connection)

        # Set user
        user_id = "test_user_123"
        session.set_user(user_id)

        # Verify user set
        assert session.user_id == user_id

    def test_set_character(self) -> None:
        """Test setting character ID on session."""
        mock_connection = Mock(spec=Connection)
        mock_connection.id = UUID("12345678-1234-5678-1234-567812345678")
        mock_connection.ip_address = "127.0.0.1"
        session = Session(mock_connection)

        # Set character
        character_id = "test_char_456"
        session.set_character(character_id)

        # Verify character set
        assert session.character_id == character_id

    def test_set_state(self) -> None:
        """Test session state transitions."""
        mock_connection = Mock(spec=Connection)
        mock_connection.id = UUID("12345678-1234-5678-1234-567812345678")
        mock_connection.ip_address = "127.0.0.1"
        session = Session(mock_connection)

        # Initial state
        assert session.state == SessionState.CONNECTED

        # Transition to authenticating
        session.set_state(SessionState.AUTHENTICATING)
        assert session.state == SessionState.AUTHENTICATING

        # Transition to playing
        session.set_state(SessionState.PLAYING)
        assert session.state == SessionState.PLAYING

        # Transition to disconnected
        session.set_state(SessionState.DISCONNECTED)
        assert session.state == SessionState.DISCONNECTED

    def test_session_string_representation(self) -> None:
        """Test session string representations."""
        mock_connection = Mock(spec=Connection)
        mock_connection.id = UUID("12345678-1234-5678-1234-567812345678")
        mock_connection.ip_address = "127.0.0.1"
        session = Session(mock_connection)

        # Test __str__
        str_repr = str(session)
        assert "Session" in str_repr
        assert str(session.id) in str_repr
        assert session.state.value in str_repr

        # Test __repr__
        repr_str = repr(session)
        assert "Session" in repr_str
        assert f"id={session.id}" in repr_str


class TestSessionManager:
    """Test cases for SessionManager class."""

    def test_session_manager_initialization(self) -> None:
        """Test creating a new session manager."""
        manager = SessionManager()

        # Verify initialization
        assert manager.get_session_count() == 0
        assert len(manager) == 0
        assert manager.get_all_sessions() == []

    def test_create_session(self) -> None:
        """Test creating a session through the manager."""
        manager = SessionManager()
        mock_connection = Mock(spec=Connection)
        mock_connection.id = UUID("12345678-1234-5678-1234-567812345678")
        mock_connection.ip_address = "127.0.0.1"

        # Create session
        session = manager.create_session(mock_connection)

        # Verify session created
        assert isinstance(session, Session)
        assert session.connection == mock_connection
        assert mock_connection.session == session
        assert manager.get_session_count() == 1

    def test_get_session(self) -> None:
        """Test retrieving a session by ID."""
        manager = SessionManager()
        mock_connection = Mock(spec=Connection)
        mock_connection.id = UUID("12345678-1234-5678-1234-567812345678")
        mock_connection.ip_address = "127.0.0.1"

        # Create session
        session = manager.create_session(mock_connection)

        # Retrieve session
        retrieved = manager.get_session(session.id)
        assert retrieved == session

        # Try non-existent session
        fake_id = UUID("00000000-0000-0000-0000-000000000000")
        assert manager.get_session(fake_id) is None

    def test_get_session_by_user(self) -> None:
        """Test retrieving a session by user ID."""
        manager = SessionManager()
        mock_connection = Mock(spec=Connection)
        mock_connection.id = UUID("12345678-1234-5678-1234-567812345678")
        mock_connection.ip_address = "127.0.0.1"

        # Create session and set user
        session = manager.create_session(mock_connection)
        session.set_user("test_user_123")

        # Retrieve by user ID
        retrieved = manager.get_session_by_user("test_user_123")
        assert retrieved == session

        # Try non-existent user
        assert manager.get_session_by_user("nonexistent") is None

    def test_destroy_session(self) -> None:
        """Test destroying a session."""
        manager = SessionManager()
        mock_connection = Mock(spec=Connection)
        mock_connection.id = UUID("12345678-1234-5678-1234-567812345678")
        mock_connection.ip_address = "127.0.0.1"

        # Create session
        session = manager.create_session(mock_connection)
        session_id = session.id

        # Verify session exists
        assert manager.get_session_count() == 1

        # Destroy session
        result = manager.destroy_session(session_id)
        assert result is True
        assert manager.get_session_count() == 0
        assert manager.get_session(session_id) is None
        assert session.state == SessionState.DISCONNECTED

        # Try destroying non-existent session
        result = manager.destroy_session(session_id)
        assert result is False

    def test_update_activity(self) -> None:
        """Test updating session activity through manager."""
        manager = SessionManager()
        mock_connection = Mock(spec=Connection)
        mock_connection.id = UUID("12345678-1234-5678-1234-567812345678")
        mock_connection.ip_address = "127.0.0.1"

        # Create session
        session = manager.create_session(mock_connection)
        initial_activity = session.last_activity

        # Wait and update
        import time

        time.sleep(0.01)
        manager.update_activity(session.id)

        # Verify activity updated
        assert session.last_activity > initial_activity

    def test_cleanup_expired(self) -> None:
        """Test cleaning up expired sessions."""
        manager = SessionManager()

        # Create active session
        mock_connection1 = Mock(spec=Connection)
        mock_connection1.id = UUID("12345678-1234-5678-1234-567812345671")
        mock_connection1.ip_address = "127.0.0.1"
        active_session = manager.create_session(mock_connection1)

        # Create expired session
        mock_connection2 = Mock(spec=Connection)
        mock_connection2.id = UUID("12345678-1234-5678-1234-567812345672")
        mock_connection2.ip_address = "127.0.0.2"
        expired_session = manager.create_session(mock_connection2)
        expired_session.last_activity = datetime.now(timezone.utc) - timedelta(minutes=61)

        # Verify both sessions exist
        assert manager.get_session_count() == 2

        # Cleanup expired
        removed_count = manager.cleanup_expired()

        # Verify only expired session removed
        assert removed_count == 1
        assert manager.get_session_count() == 1
        assert manager.get_session(active_session.id) is not None
        assert manager.get_session(expired_session.id) is None

    def test_get_all_sessions(self) -> None:
        """Test retrieving all sessions."""
        manager = SessionManager()

        # Create multiple sessions
        sessions = []
        for i in range(3):
            mock_connection = Mock(spec=Connection)
            mock_connection.id = UUID(f"12345678-1234-5678-1234-56781234567{i}")
            mock_connection.ip_address = f"127.0.0.{i}"
            session = manager.create_session(mock_connection)
            sessions.append(session)

        # Get all sessions
        all_sessions = manager.get_all_sessions()

        # Verify all returned
        assert len(all_sessions) == 3
        for session in sessions:
            assert session in all_sessions

    def test_multiple_sessions_same_manager(self) -> None:
        """Test managing multiple sessions simultaneously."""
        manager = SessionManager()

        # Create multiple sessions
        sessions = []
        for i in range(5):
            mock_connection = Mock(spec=Connection)
            mock_connection.id = UUID(f"00000000-0000-0000-0000-00000000000{i}")
            mock_connection.ip_address = f"127.0.0.{i}"
            session = manager.create_session(mock_connection)
            sessions.append(session)

        # Verify count
        assert manager.get_session_count() == 5
        assert len(manager) == 5

        # Destroy one session
        manager.destroy_session(sessions[2].id)
        assert manager.get_session_count() == 4

        # Verify correct sessions remain
        assert manager.get_session(sessions[0].id) is not None
        assert manager.get_session(sessions[1].id) is not None
        assert manager.get_session(sessions[2].id) is None
        assert manager.get_session(sessions[3].id) is not None
        assert manager.get_session(sessions[4].id) is not None


class TestSessionStateTransitions:
    """Test session state transition logic."""

    def test_typical_login_flow(self) -> None:
        """Test typical state transitions during login."""
        mock_connection = Mock(spec=Connection)
        mock_connection.id = UUID("12345678-1234-5678-1234-567812345678")
        mock_connection.ip_address = "127.0.0.1"
        session = Session(mock_connection)

        # Initial state
        assert session.state == SessionState.CONNECTED

        # Start authentication
        session.set_state(SessionState.AUTHENTICATING)
        assert session.state == SessionState.AUTHENTICATING

        # Login successful
        session.set_user("user123")
        session.set_state(SessionState.PLAYING)
        assert session.state == SessionState.PLAYING
        assert session.user_id == "user123"

        # Disconnect
        session.set_state(SessionState.DISCONNECTED)
        assert session.state == SessionState.DISCONNECTED

    def test_character_selection_flow(self) -> None:
        """Test state with character selection."""
        mock_connection = Mock(spec=Connection)
        mock_connection.id = UUID("12345678-1234-5678-1234-567812345678")
        mock_connection.ip_address = "127.0.0.1"
        session = Session(mock_connection)

        # Authenticate
        session.set_state(SessionState.AUTHENTICATING)
        session.set_user("user123")

        # Select character
        session.set_character("char456")
        session.set_state(SessionState.PLAYING)

        # Verify both set
        assert session.user_id == "user123"
        assert session.character_id == "char456"
        assert session.state == SessionState.PLAYING
