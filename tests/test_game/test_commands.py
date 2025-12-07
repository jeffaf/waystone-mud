"""Tests for game commands and command system."""

import asyncio
import uuid
from typing import AsyncGenerator
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import select

from waystone.database.engine import get_session, init_db
from waystone.database.models import Character, CharacterBackground, User
from waystone.game.commands.auth import LoginCommand, RegisterCommand
from waystone.game.commands.base import CommandContext, CommandRegistry, get_registry
from waystone.game.commands.character import CharactersCommand, CreateCommand
from waystone.game.commands.movement import LookCommand, NorthCommand
from waystone.game.engine import GameEngine
from waystone.game.world import Room
from waystone.network import Connection, Session, SessionState


@pytest.fixture
async def test_engine() -> AsyncGenerator[GameEngine, None]:
    """Create a test game engine with minimal world."""
    await init_db()

    # Reset global registry before each test
    import waystone.game.commands.base as base_module
    base_module._registry = None

    engine = GameEngine()

    # Create minimal test world
    engine.world = {
        "test_room_1": Room(
            id="test_room_1",
            name="Test Room 1",
            area="test",
            description="A test room.",
            exits={"north": "test_room_2"},
        ),
        "test_room_2": Room(
            id="test_room_2",
            name="Test Room 2",
            area="test",
            description="Another test room.",
            exits={"south": "test_room_1"},
        ),
    }

    # Register commands
    engine._register_commands()

    yield engine

    # Cleanup
    await engine.stop()

    # Reset registry after test
    base_module._registry = None


@pytest.fixture
def mock_connection() -> Connection:
    """Create a mock connection for testing."""
    connection = Mock(spec=Connection)
    connection.id = uuid.uuid4()
    connection.ip_address = "127.0.0.1"
    connection.send_line = AsyncMock()
    connection.send = AsyncMock()
    connection.readline = AsyncMock()
    connection.is_closed = False
    return connection


@pytest.fixture
def mock_session(mock_connection: Connection) -> Session:
    """Create a mock session for testing."""
    session = Session(mock_connection)
    mock_connection.session = session
    return session


@pytest.mark.asyncio
async def test_command_registry():
    """Test command registry registration and lookup."""
    registry = CommandRegistry()

    # Create test command
    cmd = RegisterCommand()

    # Register command
    registry.register(cmd)

    # Test direct lookup
    assert registry.get("register") == cmd

    # Test command count
    assert len(registry.get_all_commands()) == 1


@pytest.mark.asyncio
async def test_register_command(
    test_engine: GameEngine,
    mock_connection: Connection,
    mock_session: Session,
):
    """Test user registration command."""
    cmd = RegisterCommand()

    ctx = CommandContext(
        session=mock_session,
        connection=mock_connection,
        engine=test_engine,
        args=["testuser", "testpass123", "test@example.com"],
        raw_input="register testuser testpass123 test@example.com",
    )

    await cmd.execute(ctx)

    # Verify user was created
    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.username == "testuser")
        )
        user = result.scalar_one_or_none()

        assert user is not None
        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.verify_password("testpass123")

    # Verify success message was sent
    mock_connection.send_line.assert_called()


@pytest.mark.asyncio
async def test_login_command(
    test_engine: GameEngine,
    mock_connection: Connection,
    mock_session: Session,
):
    """Test login command."""
    # Create test user
    username = f"logintest{uuid.uuid4().hex[:8]}"
    async with get_session() as session:
        user = User(
            username=username,
            email=f"login{uuid.uuid4().hex[:8]}@example.com",
            password_hash=User.hash_password("password123"),
        )
        session.add(user)
        await session.commit()
        user_id = str(user.id)

    cmd = LoginCommand()

    ctx = CommandContext(
        session=mock_session,
        connection=mock_connection,
        engine=test_engine,
        args=[username, "password123"],
        raw_input=f"login {username} password123",
    )

    await cmd.execute(ctx)

    # Verify session was updated
    assert mock_session.user_id == user_id
    assert mock_session.state == SessionState.AUTHENTICATING

    # Verify welcome message was sent
    mock_connection.send_line.assert_called()


@pytest.mark.asyncio
async def test_login_invalid_password(
    test_engine: GameEngine,
    mock_connection: Connection,
    mock_session: Session,
):
    """Test login with invalid password."""
    # Create test user
    username = f"badpasstest{uuid.uuid4().hex[:8]}"
    async with get_session() as session:
        user = User(
            username=username,
            email=f"badpass{uuid.uuid4().hex[:8]}@example.com",
            password_hash=User.hash_password("correctpass"),
        )
        session.add(user)
        await session.commit()

    cmd = LoginCommand()

    ctx = CommandContext(
        session=mock_session,
        connection=mock_connection,
        engine=test_engine,
        args=[username, "wrongpass"],
        raw_input=f"login {username} wrongpass",
    )

    await cmd.execute(ctx)

    # Verify session was NOT updated
    assert mock_session.user_id is None
    assert mock_session.state == SessionState.CONNECTED


@pytest.mark.asyncio
async def test_characters_command(
    test_engine: GameEngine,
    mock_connection: Connection,
    mock_session: Session,
):
    """Test listing characters."""
    # Create test user and character
    char_name = f"TestChar{uuid.uuid4().hex[:8]}"
    async with get_session() as session:
        user = User(
            username=f"chartest{uuid.uuid4().hex[:8]}",
            email=f"char{uuid.uuid4().hex[:8]}@example.com",
            password_hash=User.hash_password("password"),
        )
        session.add(user)
        await session.flush()

        character = Character(
            user_id=user.id,
            name=char_name,
            background=CharacterBackground.SCHOLAR,
            current_room_id="test_room_1",
        )
        session.add(character)
        await session.commit()

        mock_session.user_id = str(user.id)

    cmd = CharactersCommand()

    ctx = CommandContext(
        session=mock_session,
        connection=mock_connection,
        engine=test_engine,
        args=[],
        raw_input="characters",
    )

    await cmd.execute(ctx)

    # Verify character list was displayed
    mock_connection.send_line.assert_called()
    calls = [str(call) for call in mock_connection.send_line.call_args_list]
    assert any(char_name in str(call) for call in calls)


@pytest.mark.asyncio
async def test_movement_command(
    test_engine: GameEngine,
    mock_connection: Connection,
    mock_session: Session,
):
    """Test movement between rooms."""
    # Create test user and character
    async with get_session() as session:
        user = User(
            username=f"movetest{uuid.uuid4().hex[:8]}",
            email=f"move{uuid.uuid4().hex[:8]}@example.com",
            password_hash=User.hash_password("password"),
        )
        session.add(user)
        await session.flush()

        character = Character(
            user_id=user.id,
            name=f"MoveChar{uuid.uuid4().hex[:8]}",
            background=CharacterBackground.WAYFARER,
            current_room_id="test_room_1",
        )
        session.add(character)
        await session.commit()

        char_id = str(character.id)
        mock_session.user_id = str(user.id)
        mock_session.character_id = char_id
        mock_session.state = SessionState.PLAYING

        # Add character to room
        test_engine.world["test_room_1"].add_player(char_id)
        test_engine.character_to_session[char_id] = mock_session

    cmd = NorthCommand()

    ctx = CommandContext(
        session=mock_session,
        connection=mock_connection,
        engine=test_engine,
        args=[],
        raw_input="north",
    )

    await cmd.execute(ctx)

    # Verify character moved to new room
    async with get_session() as session:
        result = await session.execute(
            select(Character).where(Character.id == uuid.UUID(char_id))
        )
        character = result.scalar_one_or_none()

        assert character is not None
        assert character.current_room_id == "test_room_2"

    # Verify player was removed from old room and added to new
    assert char_id not in test_engine.world["test_room_1"].players
    assert char_id in test_engine.world["test_room_2"].players


@pytest.mark.asyncio
async def test_look_command(
    test_engine: GameEngine,
    mock_connection: Connection,
    mock_session: Session,
):
    """Test looking at current room."""
    # Create test character
    async with get_session() as session:
        user = User(
            username=f"looktest{uuid.uuid4().hex[:8]}",
            email=f"look{uuid.uuid4().hex[:8]}@example.com",
            password_hash=User.hash_password("password"),
        )
        session.add(user)
        await session.flush()

        character = Character(
            user_id=user.id,
            name=f"LookChar{uuid.uuid4().hex[:8]}",
            background=CharacterBackground.SCHOLAR,
            current_room_id="test_room_1",
        )
        session.add(character)
        await session.commit()

        char_id = str(character.id)
        mock_session.character_id = char_id
        mock_session.state = SessionState.PLAYING

    cmd = LookCommand()

    ctx = CommandContext(
        session=mock_session,
        connection=mock_connection,
        engine=test_engine,
        args=[],
        raw_input="look",
    )

    await cmd.execute(ctx)

    # Verify room description was sent
    mock_connection.send_line.assert_called()
    calls = [str(call) for call in mock_connection.send_line.call_args_list]
    assert any("Test Room 1" in str(call) for call in calls)


@pytest.mark.asyncio
async def test_command_requires_character(
    test_engine: GameEngine,
    mock_connection: Connection,
    mock_session: Session,
):
    """Test that commands requiring a character are blocked without one."""
    mock_session.state = SessionState.AUTHENTICATING
    mock_session.character_id = None

    cmd = NorthCommand()

    ctx = CommandContext(
        session=mock_session,
        connection=mock_connection,
        engine=test_engine,
        args=[],
        raw_input="north",
    )

    await cmd.execute(ctx)

    # Verify error message was sent
    mock_connection.send_line.assert_called()
    calls = [str(call) for call in mock_connection.send_line.call_args_list]
    assert any("must be playing a character" in str(call).lower() for call in calls)


@pytest.mark.asyncio
async def test_engine_process_command(test_engine: GameEngine):
    """Test engine command processing."""
    # Create mock connection and session
    connection = Mock(spec=Connection)
    connection.id = uuid.uuid4()
    connection.ip_address = "127.0.0.1"
    connection.send_line = AsyncMock()
    connection.send = AsyncMock()

    session = Session(connection)
    connection.session = session

    # Test help command
    await test_engine.process_command(session, "help")

    # Verify command was processed
    connection.send_line.assert_called()


@pytest.mark.asyncio
async def test_engine_broadcast_to_room(test_engine: GameEngine):
    """Test broadcasting messages to a room."""
    # Create mock sessions
    session1 = Mock(spec=Session)
    session1.id = uuid.uuid4()
    session1.connection = Mock(spec=Connection)
    session1.connection.send_line = AsyncMock()

    session2 = Mock(spec=Session)
    session2.id = uuid.uuid4()
    session2.connection = Mock(spec=Connection)
    session2.connection.send_line = AsyncMock()

    # Add characters to room
    char_id_1 = str(uuid.uuid4())
    char_id_2 = str(uuid.uuid4())

    test_engine.world["test_room_1"].add_player(char_id_1)
    test_engine.world["test_room_1"].add_player(char_id_2)

    test_engine.character_to_session[char_id_1] = session1
    test_engine.character_to_session[char_id_2] = session2

    # Broadcast message
    test_engine.broadcast_to_room("test_room_1", "Test message")

    # Wait for async tasks
    await asyncio.sleep(0.1)

    # Both sessions should receive message
    assert session1.connection.send_line.called
    assert session2.connection.send_line.called


@pytest.mark.asyncio
async def test_engine_broadcast_exclude(test_engine: GameEngine):
    """Test broadcasting with exclusion."""
    session1 = Mock(spec=Session)
    session1.id = uuid.uuid4()
    session1.connection = Mock(spec=Connection)
    session1.connection.send_line = AsyncMock()

    session2 = Mock(spec=Session)
    session2.id = uuid.uuid4()
    session2.connection = Mock(spec=Connection)
    session2.connection.send_line = AsyncMock()

    char_id_1 = str(uuid.uuid4())
    char_id_2 = str(uuid.uuid4())

    test_engine.world["test_room_1"].add_player(char_id_1)
    test_engine.world["test_room_1"].add_player(char_id_2)

    test_engine.character_to_session[char_id_1] = session1
    test_engine.character_to_session[char_id_2] = session2

    # Broadcast excluding session1
    test_engine.broadcast_to_room("test_room_1", "Test message", exclude=session1.id)

    # Wait for async tasks
    await asyncio.sleep(0.1)

    # Only session2 should receive message
    assert not session1.connection.send_line.called
    assert session2.connection.send_line.called
