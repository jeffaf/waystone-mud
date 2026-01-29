"""Tests for the Simulated Players system - Phase 1 Core Infrastructure.

These tests verify the foundational components of the simulated player system:
- SimulatedPlayerManager initialization and basic operations
- SimulatedCommandContext for capturing command output
- SimulatedSession and SimulatedConnection for fake sessions
- Character.is_simulated field on the database model
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from waystone.database.models import Character, CharacterBackground, User


# =============================================================================
# Character.is_simulated Field Tests
# =============================================================================


@pytest.mark.asyncio
async def test_character_is_simulated_default_false(db_session: AsyncSession):
    """Test that Character.is_simulated defaults to False for new characters."""
    # Create a user first
    user = User(
        username="testuser_sim",
        email="sim@example.com",
        password_hash=User.hash_password("password123"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    # Create a character without specifying is_simulated
    character = Character(
        user_id=user.id,
        name="TestPlayer",
        background=CharacterBackground.SCHOLAR,
        current_room_id="university_main_gates",
    )
    db_session.add(character)
    await db_session.commit()
    await db_session.refresh(character)

    # Verify default is False
    assert character.is_simulated is False


@pytest.mark.asyncio
async def test_character_can_be_marked_simulated(db_session: AsyncSession):
    """Test that a character can be explicitly marked as simulated."""
    # Create a user first
    user = User(
        username="testuser_sim2",
        email="sim2@example.com",
        password_hash=User.hash_password("password123"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    # Create a simulated character
    character = Character(
        user_id=user.id,
        name="SimPlayer",
        background=CharacterBackground.WAYFARER,
        current_room_id="university_main_gates",
        is_simulated=True,
    )
    db_session.add(character)
    await db_session.commit()
    await db_session.refresh(character)

    # Verify it was set to True
    assert character.is_simulated is True


@pytest.mark.asyncio
async def test_can_query_simulated_characters(db_session: AsyncSession):
    """Test that we can query for simulated vs real characters."""
    from sqlalchemy import select

    # Create a user
    user = User(
        username="testuser_sim3",
        email="sim3@example.com",
        password_hash=User.hash_password("password123"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    # Create one real and one simulated character
    real_char = Character(
        user_id=user.id,
        name="RealPlayer",
        background=CharacterBackground.SCHOLAR,
        current_room_id="university_main_gates",
        is_simulated=False,
    )
    sim_char = Character(
        user_id=user.id,
        name="SimBot",
        background=CharacterBackground.WAYFARER,
        current_room_id="university_main_gates",
        is_simulated=True,
    )
    db_session.add_all([real_char, sim_char])
    await db_session.commit()

    # Query for simulated characters
    result = await db_session.execute(
        select(Character).where(Character.is_simulated == True)  # noqa: E712
    )
    simulated = result.scalars().all()
    assert len(simulated) == 1
    assert simulated[0].name == "SimBot"

    # Query for real characters
    result = await db_session.execute(
        select(Character).where(Character.is_simulated == False)  # noqa: E712
    )
    real = result.scalars().all()
    assert len(real) == 1
    assert real[0].name == "RealPlayer"


# =============================================================================
# SimulatedConnection Tests
# =============================================================================


@pytest.mark.asyncio
async def test_simulated_connection_captures_output():
    """Test that SimulatedConnection captures output to buffer."""
    from waystone.game.systems.simulated_players import SimulatedConnection

    conn = SimulatedConnection()

    # Should start with empty buffer
    assert conn.output_buffer == []
    assert conn.is_closed is False

    # Send some messages
    await conn.send_line("Hello, world!")
    await conn.send("Test message")

    # Verify buffer captured output
    assert len(conn.output_buffer) == 2
    assert conn.output_buffer[0] == "Hello, world!"
    assert conn.output_buffer[1] == "Test message"


@pytest.mark.asyncio
async def test_simulated_connection_clear_buffer():
    """Test that SimulatedConnection buffer can be cleared."""
    from waystone.game.systems.simulated_players import SimulatedConnection

    conn = SimulatedConnection()

    await conn.send_line("Message 1")
    await conn.send_line("Message 2")
    assert len(conn.output_buffer) == 2

    conn.clear_buffer()
    assert conn.output_buffer == []


def test_simulated_connection_close():
    """Test that SimulatedConnection can be closed."""
    from waystone.game.systems.simulated_players import SimulatedConnection

    conn = SimulatedConnection()
    assert conn.is_closed is False

    conn.close()
    assert conn.is_closed is True


# =============================================================================
# SimulatedSession Tests
# =============================================================================


def test_simulated_session_has_character_id():
    """Test that SimulatedSession holds a character ID."""
    from waystone.game.systems.simulated_players import SimulatedSession

    char_id = uuid.uuid4()
    session = SimulatedSession(character_id=str(char_id))

    assert session.character_id == str(char_id)
    assert session.is_simulated is True


def test_simulated_session_has_correct_state():
    """Test that SimulatedSession starts in PLAYING state."""
    from waystone.game.systems.simulated_players import SimulatedSession
    from waystone.network import SessionState

    char_id = uuid.uuid4()
    session = SimulatedSession(character_id=str(char_id))

    assert session.state == SessionState.PLAYING


def test_simulated_session_has_unique_id():
    """Test that each SimulatedSession has a unique ID."""
    from waystone.game.systems.simulated_players import SimulatedSession

    session1 = SimulatedSession(character_id=str(uuid.uuid4()))
    session2 = SimulatedSession(character_id=str(uuid.uuid4()))

    assert session1.id != session2.id


def test_simulated_session_connection_property():
    """Test that SimulatedSession has a connection property."""
    from waystone.game.systems.simulated_players import (
        SimulatedConnection,
        SimulatedSession,
    )

    session = SimulatedSession(character_id=str(uuid.uuid4()))

    # Should have an associated connection
    assert isinstance(session.connection, SimulatedConnection)


# =============================================================================
# SimulatedCommandContext Tests
# =============================================================================


def test_simulated_context_creation():
    """Test that SimulatedCommandContext can be created."""
    from waystone.game.systems.simulated_players import (
        SimulatedCommandContext,
        SimulatedSession,
    )

    session = SimulatedSession(character_id=str(uuid.uuid4()))

    # Mock engine for context (we just need it to exist for type checking)
    ctx = SimulatedCommandContext(
        session=session,
        engine=None,  # type: ignore - we don't need a real engine for this test
        args=["test", "arg"],
        raw_input="test arg",
    )

    assert ctx.session == session
    assert ctx.connection == session.connection
    assert ctx.args == ["test", "arg"]
    assert ctx.raw_input == "test arg"


@pytest.mark.asyncio
async def test_simulated_context_captures_command_output():
    """Test that commands executed via SimulatedCommandContext capture output."""
    from waystone.game.systems.simulated_players import (
        SimulatedCommandContext,
        SimulatedSession,
    )

    session = SimulatedSession(character_id=str(uuid.uuid4()))
    ctx = SimulatedCommandContext(
        session=session,
        engine=None,  # type: ignore
        args=[],
        raw_input="test",
    )

    # Simulate command output
    await ctx.connection.send_line("You look around.")
    await ctx.connection.send_line("You see nothing special.")

    # Verify output was captured
    assert len(ctx.connection.output_buffer) == 2
    assert "You look around." in ctx.connection.output_buffer[0]


# =============================================================================
# SimulatedPlayerManager Tests
# =============================================================================


def test_manager_initialization():
    """Test that SimulatedPlayerManager initializes correctly."""
    from waystone.game.systems.simulated_players import SimulatedPlayerManager

    manager = SimulatedPlayerManager()

    assert manager.active_sims == {}
    assert manager.enabled is True


def test_manager_get_active_empty():
    """Test that get_active returns empty list when no sims active."""
    from waystone.game.systems.simulated_players import SimulatedPlayerManager

    manager = SimulatedPlayerManager()
    active = manager.get_active()

    assert active == []
    assert isinstance(active, list)


def test_manager_can_be_disabled():
    """Test that the manager can be disabled."""
    from waystone.game.systems.simulated_players import SimulatedPlayerManager

    manager = SimulatedPlayerManager()
    assert manager.enabled is True

    manager.enabled = False
    assert manager.enabled is False


@pytest.mark.asyncio
async def test_manager_tick_does_not_crash():
    """Test that tick() runs without error when no sims are active."""
    from waystone.game.systems.simulated_players import SimulatedPlayerManager

    manager = SimulatedPlayerManager()

    # Should not raise any exceptions
    await manager.tick(None)  # type: ignore - passing None as engine for skeleton


@pytest.mark.asyncio
async def test_manager_tick_returns_action_count():
    """Test that tick() returns the number of actions taken."""
    from waystone.game.systems.simulated_players import SimulatedPlayerManager

    manager = SimulatedPlayerManager()

    # With no active sims, should return 0
    actions = await manager.tick(None)  # type: ignore
    assert actions == 0


# =============================================================================
# get_sim_manager Singleton Tests
# =============================================================================


def test_get_sim_manager_returns_manager():
    """Test that get_sim_manager returns a SimulatedPlayerManager instance."""
    from waystone.game.systems.simulated_players import (
        SimulatedPlayerManager,
        get_sim_manager,
    )

    manager = get_sim_manager()
    assert isinstance(manager, SimulatedPlayerManager)


def test_get_sim_manager_returns_same_instance():
    """Test that get_sim_manager returns the same singleton instance."""
    from waystone.game.systems.simulated_players import get_sim_manager

    manager1 = get_sim_manager()
    manager2 = get_sim_manager()

    assert manager1 is manager2
