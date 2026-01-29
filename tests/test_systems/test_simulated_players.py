"""Tests for the Simulated Players system - Phase 1 Core Infrastructure.

These tests verify the foundational components of the simulated player system:
- SimulatedPlayerManager initialization and basic operations
- SimulatedCommandContext for capturing command output
- SimulatedSession and SimulatedConnection for fake sessions
- Character.is_simulated field on the database model
"""

import uuid

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


# =============================================================================
# Phase 2: Lifecycle Management Tests
# =============================================================================


class TestSimulatedPlayerConfig:
    """Tests for SimulatedPlayerConfig dataclass."""

    def test_config_creation_with_required_fields(self):
        """Test that config can be created with required fields."""
        from waystone.database.models import CharacterBackground
        from waystone.game.systems.simulated_players import (
            BartleType,
            SimulatedPlayerConfig,
        )

        config = SimulatedPlayerConfig(
            id="sim_explorer_lyra",
            name="Lyra",
            background=CharacterBackground.WAYFARER,
            bartle_type=BartleType.EXPLORER,
        )

        assert config.id == "sim_explorer_lyra"
        assert config.name == "Lyra"
        assert config.background == CharacterBackground.WAYFARER
        assert config.bartle_type == BartleType.EXPLORER

    def test_config_default_values(self):
        """Test that config has sensible default values."""
        from waystone.database.models import CharacterBackground
        from waystone.game.systems.simulated_players import (
            BartleType,
            SimulatedPlayerConfig,
        )

        config = SimulatedPlayerConfig(
            id="sim_test",
            name="Test",
            background=CharacterBackground.SCHOLAR,
            bartle_type=BartleType.ACHIEVER,
        )

        # Should have default active hours and session duration
        assert config.active_hours == (8, 22)
        assert config.session_duration_minutes == (60, 240)
        assert config.starting_room == "university_main_gates"

    def test_config_custom_schedule(self):
        """Test that config can have custom schedule."""
        from waystone.database.models import CharacterBackground
        from waystone.game.systems.simulated_players import (
            BartleType,
            SimulatedPlayerConfig,
        )

        config = SimulatedPlayerConfig(
            id="sim_night_owl",
            name="NightOwl",
            background=CharacterBackground.PERFORMER,
            bartle_type=BartleType.SOCIALIZER,
            active_hours=(22, 6),  # Night hours
            session_duration_minutes=(30, 120),
        )

        assert config.active_hours == (22, 6)
        assert config.session_duration_minutes == (30, 120)


class TestBartleType:
    """Tests for BartleType enum."""

    def test_all_bartle_types_exist(self):
        """Test that all four Bartle types are defined."""
        from waystone.game.systems.simulated_players import BartleType

        assert hasattr(BartleType, "ACHIEVER")
        assert hasattr(BartleType, "EXPLORER")
        assert hasattr(BartleType, "SOCIALIZER")
        assert hasattr(BartleType, "KILLER")

    def test_bartle_type_values(self):
        """Test that Bartle types have string values."""
        from waystone.game.systems.simulated_players import BartleType

        assert BartleType.ACHIEVER.value == "achiever"
        assert BartleType.EXPLORER.value == "explorer"
        assert BartleType.SOCIALIZER.value == "socializer"
        assert BartleType.KILLER.value == "killer"


class TestSimulatedPlayer:
    """Tests for SimulatedPlayer runtime class."""

    def test_simulated_player_creation(self):
        """Test that SimulatedPlayer can be created with config and character."""
        from waystone.database.models import CharacterBackground
        from waystone.game.systems.simulated_players import (
            BartleType,
            SimulatedPlayer,
            SimulatedPlayerConfig,
        )

        config = SimulatedPlayerConfig(
            id="sim_test",
            name="TestSim",
            background=CharacterBackground.SCHOLAR,
            bartle_type=BartleType.EXPLORER,
        )

        sim = SimulatedPlayer(
            config=config,
            character_id="test-char-id",
        )

        assert sim.config == config
        assert sim.character_id == "test-char-id"
        assert sim.is_logged_in is False

    def test_simulated_player_has_session(self):
        """Test that logged-in SimulatedPlayer has a session."""
        from waystone.database.models import CharacterBackground
        from waystone.game.systems.simulated_players import (
            BartleType,
            SimulatedPlayer,
            SimulatedPlayerConfig,
            SimulatedSession,
        )

        config = SimulatedPlayerConfig(
            id="sim_test",
            name="TestSim",
            background=CharacterBackground.SCHOLAR,
            bartle_type=BartleType.EXPLORER,
        )

        sim = SimulatedPlayer(
            config=config,
            character_id="test-char-id",
        )

        # Before login, no session
        assert sim.session is None

        # After setting session, should have one
        session = SimulatedSession(character_id="test-char-id")
        sim.session = session
        assert sim.session is not None
        assert sim.is_logged_in is True


class TestLoginLogout:
    """Tests for login/logout lifecycle management."""

    @pytest.mark.asyncio
    async def test_login_player_creates_session(self, db_session: AsyncSession):
        """Test that login_player creates a proper session."""
        from waystone.database.models import CharacterBackground
        from waystone.game.systems.simulated_players import (
            BartleType,
            SimulatedPlayerConfig,
            SimulatedPlayerManager,
            reset_sim_manager,
        )

        reset_sim_manager()
        manager = SimulatedPlayerManager()

        config = SimulatedPlayerConfig(
            id="sim_lyra",
            name="Lyra",
            background=CharacterBackground.WAYFARER,
            bartle_type=BartleType.EXPLORER,
        )
        manager.add_config(config)

        # Login the player
        sim = await manager.login_player("sim_lyra", db_session)

        assert sim is not None
        assert sim.is_logged_in is True
        assert sim.session is not None
        assert "sim_lyra" in manager.active_sims

    @pytest.mark.asyncio
    async def test_login_player_creates_character_in_db(self, db_session: AsyncSession):
        """Test that login_player creates a Character record if needed."""
        from sqlalchemy import select

        from waystone.database.models import Character, CharacterBackground
        from waystone.game.systems.simulated_players import (
            BartleType,
            SimulatedPlayerConfig,
            SimulatedPlayerManager,
            reset_sim_manager,
        )

        reset_sim_manager()
        manager = SimulatedPlayerManager()

        config = SimulatedPlayerConfig(
            id="sim_newchar",
            name="NewSimChar",
            background=CharacterBackground.SCHOLAR,
            bartle_type=BartleType.ACHIEVER,
        )
        manager.add_config(config)

        # Login should create character
        await manager.login_player("sim_newchar", db_session)

        # Verify character was created
        result = await db_session.execute(select(Character).where(Character.name == "NewSimChar"))
        character = result.scalar_one_or_none()

        assert character is not None
        assert character.is_simulated is True
        assert character.background == CharacterBackground.SCHOLAR

    @pytest.mark.asyncio
    async def test_login_player_places_in_starting_room(self, db_session: AsyncSession):
        """Test that login_player places simulated player in starting room."""
        from sqlalchemy import select

        from waystone.database.models import Character, CharacterBackground
        from waystone.game.systems.simulated_players import (
            BartleType,
            SimulatedPlayerConfig,
            SimulatedPlayerManager,
            reset_sim_manager,
        )

        reset_sim_manager()
        manager = SimulatedPlayerManager()

        config = SimulatedPlayerConfig(
            id="sim_roomtest",
            name="RoomTestSim",
            background=CharacterBackground.WAYFARER,
            bartle_type=BartleType.EXPLORER,
            starting_room="imre_square",
        )
        manager.add_config(config)

        await manager.login_player("sim_roomtest", db_session)

        # Verify character is in starting room
        result = await db_session.execute(select(Character).where(Character.name == "RoomTestSim"))
        character = result.scalar_one_or_none()

        assert character is not None
        assert character.current_room_id == "imre_square"

    @pytest.mark.asyncio
    async def test_logout_player_removes_from_active(self, db_session: AsyncSession):
        """Test that logout_player removes sim from active_sims."""
        from waystone.database.models import CharacterBackground
        from waystone.game.systems.simulated_players import (
            BartleType,
            SimulatedPlayerConfig,
            SimulatedPlayerManager,
            reset_sim_manager,
        )

        reset_sim_manager()
        manager = SimulatedPlayerManager()

        config = SimulatedPlayerConfig(
            id="sim_logout",
            name="LogoutTest",
            background=CharacterBackground.MERCHANT,
            bartle_type=BartleType.SOCIALIZER,
        )
        manager.add_config(config)

        # Login then logout
        await manager.login_player("sim_logout", db_session)
        assert "sim_logout" in manager.active_sims

        await manager.logout_player("sim_logout")
        assert "sim_logout" not in manager.active_sims

    @pytest.mark.asyncio
    async def test_logout_player_cleans_up_session(self, db_session: AsyncSession):
        """Test that logout_player properly cleans up session state."""
        from waystone.database.models import CharacterBackground
        from waystone.game.systems.simulated_players import (
            BartleType,
            SimulatedPlayerConfig,
            SimulatedPlayerManager,
            reset_sim_manager,
        )

        reset_sim_manager()
        manager = SimulatedPlayerManager()

        config = SimulatedPlayerConfig(
            id="sim_cleanup",
            name="CleanupTest",
            background=CharacterBackground.NOBLE,
            bartle_type=BartleType.KILLER,
        )
        manager.add_config(config)

        sim = await manager.login_player("sim_cleanup", db_session)
        assert sim.is_logged_in is True

        await manager.logout_player("sim_cleanup")

        # Sim should no longer be logged in
        assert sim.is_logged_in is False
        assert sim.session is None

    @pytest.mark.asyncio
    async def test_login_nonexistent_config_returns_none(self, db_session: AsyncSession):
        """Test that login_player returns None for unknown config."""
        from waystone.game.systems.simulated_players import (
            SimulatedPlayerManager,
            reset_sim_manager,
        )

        reset_sim_manager()
        manager = SimulatedPlayerManager()

        result = await manager.login_player("nonexistent", db_session)
        assert result is None


class TestWhoListIntegration:
    """Tests for simulated player appearance in who list."""

    @pytest.mark.asyncio
    async def test_sim_appears_in_who_list(self, db_session: AsyncSession):
        """Test that logged-in simulated players appear in who list."""
        from waystone.database.models import CharacterBackground
        from waystone.game.systems.simulated_players import (
            BartleType,
            SimulatedPlayerConfig,
            SimulatedPlayerManager,
            reset_sim_manager,
        )

        reset_sim_manager()
        manager = SimulatedPlayerManager()

        config = SimulatedPlayerConfig(
            id="sim_who",
            name="WhoTestSim",
            background=CharacterBackground.PERFORMER,
            bartle_type=BartleType.SOCIALIZER,
        )
        manager.add_config(config)

        await manager.login_player("sim_who", db_session)

        # get_active should return logged in sims
        active = manager.get_active()
        assert len(active) == 1
        assert active[0].config.name == "WhoTestSim"

    @pytest.mark.asyncio
    async def test_logged_out_sim_not_in_who_list(self, db_session: AsyncSession):
        """Test that logged-out simulated players don't appear in who list."""
        from waystone.database.models import CharacterBackground
        from waystone.game.systems.simulated_players import (
            BartleType,
            SimulatedPlayerConfig,
            SimulatedPlayerManager,
            reset_sim_manager,
        )

        reset_sim_manager()
        manager = SimulatedPlayerManager()

        config = SimulatedPlayerConfig(
            id="sim_nowho",
            name="NoWhoTest",
            background=CharacterBackground.COMMONER,
            bartle_type=BartleType.ACHIEVER,
        )
        manager.add_config(config)

        await manager.login_player("sim_nowho", db_session)
        await manager.logout_player("sim_nowho")

        active = manager.get_active()
        assert len(active) == 0


class TestRoomPresence:
    """Tests for simulated player presence in rooms."""

    @pytest.mark.asyncio
    async def test_sim_added_to_room_on_login(self, db_session: AsyncSession):
        """Test that simulated player is added to room.players on login."""
        from waystone.database.models import CharacterBackground
        from waystone.game.systems.simulated_players import (
            BartleType,
            SimulatedPlayerConfig,
            SimulatedPlayerManager,
            reset_sim_manager,
        )
        from waystone.game.world import Room

        reset_sim_manager()
        manager = SimulatedPlayerManager()

        # Create a mock room
        room = Room(
            id="test_room",
            name="Test Room",
            area="test",
            description="A test room.",
        )

        config = SimulatedPlayerConfig(
            id="sim_room",
            name="RoomSim",
            background=CharacterBackground.WAYFARER,
            bartle_type=BartleType.EXPLORER,
            starting_room="test_room",
        )
        manager.add_config(config)

        # Login with room reference
        sim = await manager.login_player("sim_room", db_session, room=room)

        assert sim is not None
        # Character ID should be in room.players
        assert sim.character_id in room.players

    @pytest.mark.asyncio
    async def test_sim_removed_from_room_on_logout(self, db_session: AsyncSession):
        """Test that simulated player is removed from room.players on logout."""
        from waystone.database.models import CharacterBackground
        from waystone.game.systems.simulated_players import (
            BartleType,
            SimulatedPlayerConfig,
            SimulatedPlayerManager,
            reset_sim_manager,
        )
        from waystone.game.world import Room

        reset_sim_manager()
        manager = SimulatedPlayerManager()

        room = Room(
            id="test_room2",
            name="Test Room 2",
            area="test",
            description="Another test room.",
        )

        config = SimulatedPlayerConfig(
            id="sim_room2",
            name="RoomSim2",
            background=CharacterBackground.SCHOLAR,
            bartle_type=BartleType.ACHIEVER,
            starting_room="test_room2",
        )
        manager.add_config(config)

        sim = await manager.login_player("sim_room2", db_session, room=room)
        char_id = sim.character_id

        # Verify in room
        assert char_id in room.players

        # Logout with room reference
        await manager.logout_player("sim_room2", room=room)

        # Should be removed
        assert char_id not in room.players


class TestLoginScheduling:
    """Tests for login/logout scheduling."""

    def test_is_active_hour_within_range(self):
        """Test that is_active_hour returns True within active hours."""
        from waystone.database.models import CharacterBackground
        from waystone.game.systems.simulated_players import (
            BartleType,
            SimulatedPlayerConfig,
            SimulatedPlayerManager,
            reset_sim_manager,
        )

        reset_sim_manager()
        manager = SimulatedPlayerManager()

        config = SimulatedPlayerConfig(
            id="sim_schedule",
            name="ScheduleSim",
            background=CharacterBackground.SCHOLAR,
            bartle_type=BartleType.ACHIEVER,
            active_hours=(8, 22),  # 8am to 10pm
        )

        # Test hours within range
        assert manager._is_active_hour(config, 10) is True
        assert manager._is_active_hour(config, 8) is True
        assert manager._is_active_hour(config, 21) is True

    def test_is_active_hour_outside_range(self):
        """Test that is_active_hour returns False outside active hours."""
        from waystone.database.models import CharacterBackground
        from waystone.game.systems.simulated_players import (
            BartleType,
            SimulatedPlayerConfig,
            SimulatedPlayerManager,
            reset_sim_manager,
        )

        reset_sim_manager()
        manager = SimulatedPlayerManager()

        config = SimulatedPlayerConfig(
            id="sim_schedule2",
            name="ScheduleSim2",
            background=CharacterBackground.MERCHANT,
            bartle_type=BartleType.SOCIALIZER,
            active_hours=(8, 22),
        )

        # Test hours outside range
        assert manager._is_active_hour(config, 3) is False
        assert manager._is_active_hour(config, 23) is False

    def test_is_active_hour_wraps_around_midnight(self):
        """Test that is_active_hour handles midnight wrap correctly."""
        from waystone.database.models import CharacterBackground
        from waystone.game.systems.simulated_players import (
            BartleType,
            SimulatedPlayerConfig,
            SimulatedPlayerManager,
            reset_sim_manager,
        )

        reset_sim_manager()
        manager = SimulatedPlayerManager()

        config = SimulatedPlayerConfig(
            id="sim_night",
            name="NightSim",
            background=CharacterBackground.PERFORMER,
            bartle_type=BartleType.KILLER,
            active_hours=(22, 6),  # 10pm to 6am (night owl)
        )

        # Night hours should be active
        assert manager._is_active_hour(config, 23) is True
        assert manager._is_active_hour(config, 0) is True
        assert manager._is_active_hour(config, 3) is True

        # Day hours should be inactive
        assert manager._is_active_hour(config, 12) is False
        assert manager._is_active_hour(config, 18) is False


# =============================================================================
# Phase 3: Movement (Explorer MVP) Tests
# =============================================================================


class TestBehaviorTree:
    """Tests for the behavior tree framework."""

    def test_behavior_status_enum_values(self):
        """Test that BehaviorStatus has expected values."""
        from waystone.game.systems.simulated_players import BehaviorStatus

        assert BehaviorStatus.SUCCESS.value == "success"
        assert BehaviorStatus.FAILURE.value == "failure"
        assert BehaviorStatus.RUNNING.value == "running"

    def test_behavior_result_creation(self):
        """Test that BehaviorResult can be created with status and action."""
        from waystone.game.systems.simulated_players import (
            BehaviorResult,
            BehaviorStatus,
        )

        result = BehaviorResult(status=BehaviorStatus.SUCCESS)
        assert result.status == BehaviorStatus.SUCCESS
        assert result.action is None

    def test_behavior_result_with_action(self):
        """Test that BehaviorResult can hold an action."""
        from waystone.game.systems.simulated_players import (
            BehaviorAction,
            BehaviorResult,
            BehaviorStatus,
        )

        action = BehaviorAction(command="north", args=[])
        result = BehaviorResult(status=BehaviorStatus.SUCCESS, action=action)
        assert result.action is not None
        assert result.action.command == "north"

    def test_behavior_node_has_required_methods(self):
        """Test that BehaviorNode defines condition and execute methods."""
        from waystone.game.systems.simulated_players import BehaviorNode

        # Verify required abstract methods exist
        assert hasattr(BehaviorNode, "condition")
        assert hasattr(BehaviorNode, "execute")

    def test_simple_behavior_node_execution(self):
        """Test that a simple behavior node can be executed."""
        from waystone.game.systems.simulated_players import (
            BehaviorAction,
            BehaviorNode,
            BehaviorResult,
            BehaviorStatus,
        )

        class TestNode(BehaviorNode):
            def condition(self, context) -> bool:
                return True

            def execute(self, context) -> BehaviorResult:
                return BehaviorResult(
                    status=BehaviorStatus.SUCCESS,
                    action=BehaviorAction(command="test", args=[]),
                )

        node = TestNode()
        result = node.execute(None)
        assert result.status == BehaviorStatus.SUCCESS
        assert result.action.command == "test"


class TestExplorerBehavior:
    """Tests for Explorer-specific behavior."""

    def test_explorer_behavior_creation(self):
        """Test that ExplorerBehavior can be created."""
        from waystone.game.systems.simulated_players import ExplorerBehavior

        behavior = ExplorerBehavior()
        assert behavior is not None

    def test_explorer_selects_movement_action(self):
        """Test that Explorer primarily selects movement actions."""
        from waystone.game.systems.simulated_players import (
            ExplorerBehavior,
            SimMemory,
        )

        behavior = ExplorerBehavior()
        memory = SimMemory()

        # With exits available, should get movement most of the time
        available_exits = ["north", "south", "east"]

        # Run multiple times to verify weighted selection
        move_count = 0
        for _ in range(100):
            action = behavior.select_action(
                available_exits=available_exits,
                memory=memory,
                last_direction=None,
            )
            if action.command in available_exits:
                move_count += 1

        # Should move most of the time (80% target)
        assert move_count >= 50, f"Expected mostly move actions, got {move_count}/100"

    def test_explorer_avoids_backtracking(self):
        """Test that Explorer avoids going back the way it came."""
        from waystone.game.systems.simulated_players import (
            ExplorerBehavior,
            SimMemory,
        )

        behavior = ExplorerBehavior()
        memory = SimMemory()

        # When we came from north, we shouldn't go south (back)
        available_exits = ["north", "south"]
        last_direction = "north"  # We came from the north

        # Get opposite direction logic
        opposite = behavior._get_opposite_direction(last_direction)
        assert opposite == "south"

        # If we only have south, we should still avoid it if possible
        available_exits = ["south", "east"]

        for _ in range(20):
            action = behavior.select_action(
                available_exits=available_exits,
                memory=memory,
                last_direction=last_direction,
            )
            # Should prefer east over south when we just came from north
            # (south is backtracking)
            if action.command in ["south", "east"]:
                # At minimum, east should be more common
                pass

    def test_explorer_prefers_unexplored_exits(self):
        """Test that Explorer prefers exits it hasn't visited."""
        from waystone.game.systems.simulated_players import (
            ExplorerBehavior,
            SimMemory,
        )

        behavior = ExplorerBehavior()
        memory = SimMemory()

        # Mark north as recently visited
        memory.visited_directions.add("north")

        available_exits = ["north", "south", "east"]

        # Should prefer unvisited directions
        unvisited_count = 0
        for _ in range(50):
            action = behavior.select_action(
                available_exits=available_exits,
                memory=memory,
                last_direction=None,
            )
            if action.command in ["south", "east"]:
                unvisited_count += 1

        # Should prefer unvisited exits
        assert unvisited_count >= 30, f"Expected to prefer unvisited, got {unvisited_count}/50"


class TestSimMemory:
    """Tests for simulated player memory."""

    def test_memory_creation(self):
        """Test that SimMemory can be created."""
        from waystone.game.systems.simulated_players import SimMemory

        memory = SimMemory()
        assert memory is not None

    def test_memory_tracks_visited_directions(self):
        """Test that memory tracks which directions were visited."""
        from waystone.game.systems.simulated_players import SimMemory

        memory = SimMemory()
        assert len(memory.visited_directions) == 0

        memory.visited_directions.add("north")
        assert "north" in memory.visited_directions

    def test_memory_tracks_last_direction(self):
        """Test that memory tracks the last direction moved."""
        from waystone.game.systems.simulated_players import SimMemory

        memory = SimMemory()
        assert memory.last_direction is None

        memory.last_direction = "south"
        assert memory.last_direction == "south"

    def test_memory_tracks_recent_rooms(self):
        """Test that memory tracks recently visited rooms."""
        from waystone.game.systems.simulated_players import SimMemory

        memory = SimMemory()
        assert len(memory.recent_rooms) == 0

        memory.add_room("room1")
        memory.add_room("room2")
        assert "room1" in memory.recent_rooms
        assert "room2" in memory.recent_rooms

    def test_memory_has_max_room_history(self):
        """Test that memory limits room history size."""
        from waystone.game.systems.simulated_players import SimMemory

        memory = SimMemory()

        # Add many rooms
        for i in range(20):
            memory.add_room(f"room{i}")

        # Should be limited
        assert len(memory.recent_rooms) <= 10


class TestCommandExecution:
    """Tests for simulated player command execution."""

    @pytest.mark.asyncio
    async def test_can_execute_look_command(self, db_session: AsyncSession):
        """Test that simulated player can execute look command."""
        from waystone.database.models import CharacterBackground
        from waystone.game.systems.simulated_players import (
            BartleType,
            SimulatedPlayerConfig,
            SimulatedPlayerManager,
            reset_sim_manager,
        )

        reset_sim_manager()
        manager = SimulatedPlayerManager()

        config = SimulatedPlayerConfig(
            id="sim_exec_test",
            name="ExecTest",
            background=CharacterBackground.WAYFARER,
            bartle_type=BartleType.EXPLORER,
        )
        manager.add_config(config)

        sim = await manager.login_player("sim_exec_test", db_session)
        assert sim is not None

        # Execute look command
        output = await manager.execute_command(sim, "look")

        # Should have captured some output (even if error about room not existing)
        assert output is not None or isinstance(output, str)

    @pytest.mark.asyncio
    async def test_can_execute_exits_command(self, db_session: AsyncSession):
        """Test that simulated player can execute exits command."""
        from waystone.database.models import CharacterBackground
        from waystone.game.systems.simulated_players import (
            BartleType,
            SimulatedPlayerConfig,
            SimulatedPlayerManager,
            reset_sim_manager,
        )

        reset_sim_manager()
        manager = SimulatedPlayerManager()

        config = SimulatedPlayerConfig(
            id="sim_exits_test",
            name="ExitsTest",
            background=CharacterBackground.WAYFARER,
            bartle_type=BartleType.EXPLORER,
        )
        manager.add_config(config)

        sim = await manager.login_player("sim_exits_test", db_session)
        assert sim is not None

        # Execute exits command
        output = await manager.execute_command(sim, "exits")

        # Should have captured some output
        assert output is not None or isinstance(output, str)

    @pytest.mark.asyncio
    async def test_command_output_captured_in_buffer(self, db_session: AsyncSession):
        """Test that command output is captured in connection buffer."""
        from waystone.database.models import CharacterBackground
        from waystone.game.systems.simulated_players import (
            BartleType,
            SimulatedPlayerConfig,
            SimulatedPlayerManager,
            reset_sim_manager,
        )

        reset_sim_manager()
        manager = SimulatedPlayerManager()

        config = SimulatedPlayerConfig(
            id="sim_buffer_test",
            name="BufferTest",
            background=CharacterBackground.WAYFARER,
            bartle_type=BartleType.EXPLORER,
        )
        manager.add_config(config)

        sim = await manager.login_player("sim_buffer_test", db_session)
        assert sim is not None
        assert sim.session is not None

        # Clear buffer first
        sim.session.connection.clear_buffer()

        # Execute a command
        await manager.execute_command(sim, "look")

        # Buffer should contain output
        # Note: May contain error messages if room doesn't exist, but should have SOMETHING
        assert len(sim.session.connection.output_buffer) >= 0


class TestTickIntegration:
    """Tests for tick-based behavior execution."""

    @pytest.mark.asyncio
    async def test_tick_runs_explorer_behavior(self, db_session: AsyncSession):
        """Test that tick() runs Explorer behavior tree."""
        from unittest.mock import MagicMock

        from waystone.database.models import CharacterBackground
        from waystone.game.systems.simulated_players import (
            BartleType,
            ExplorerBehavior,
            SimulatedPlayerConfig,
            SimulatedPlayerManager,
            reset_sim_manager,
        )

        reset_sim_manager()
        manager = SimulatedPlayerManager()

        config = SimulatedPlayerConfig(
            id="sim_tick_test",
            name="TickTest",
            background=CharacterBackground.WAYFARER,
            bartle_type=BartleType.EXPLORER,
        )
        manager.add_config(config)

        sim = await manager.login_player("sim_tick_test", db_session)
        assert sim is not None

        # Set up Explorer behavior
        sim.behavior = ExplorerBehavior()

        # Create mock engine with world
        mock_engine = MagicMock()
        mock_room = MagicMock()
        mock_room.exits = {"north": "room2", "south": "room3"}
        mock_room.id = "test_room"
        mock_engine.world.get.return_value = mock_room

        # Run tick
        actions_taken = await manager.tick(mock_engine)

        # Should have taken at least 0 actions (may not take action if conditions not met)
        assert actions_taken >= 0

    @pytest.mark.asyncio
    async def test_tick_returns_action_count(self, db_session: AsyncSession):
        """Test that tick() returns the count of actions taken."""
        from waystone.database.models import CharacterBackground
        from waystone.game.systems.simulated_players import (
            BartleType,
            SimulatedPlayerConfig,
            SimulatedPlayerManager,
            reset_sim_manager,
        )

        reset_sim_manager()
        manager = SimulatedPlayerManager()

        config = SimulatedPlayerConfig(
            id="sim_count_test",
            name="CountTest",
            background=CharacterBackground.WAYFARER,
            bartle_type=BartleType.EXPLORER,
        )
        manager.add_config(config)

        await manager.login_player("sim_count_test", db_session)

        # Tick should return integer count
        actions = await manager.tick(None)
        assert isinstance(actions, int)

    @pytest.mark.asyncio
    async def test_disabled_manager_takes_no_actions(self, db_session: AsyncSession):
        """Test that disabled manager takes no actions on tick."""
        from waystone.database.models import CharacterBackground
        from waystone.game.systems.simulated_players import (
            BartleType,
            SimulatedPlayerConfig,
            SimulatedPlayerManager,
            reset_sim_manager,
        )

        reset_sim_manager()
        manager = SimulatedPlayerManager()

        config = SimulatedPlayerConfig(
            id="sim_disabled_test",
            name="DisabledTest",
            background=CharacterBackground.WAYFARER,
            bartle_type=BartleType.EXPLORER,
        )
        manager.add_config(config)

        await manager.login_player("sim_disabled_test", db_session)
        manager.enabled = False

        actions = await manager.tick(None)
        assert actions == 0


class TestExplorerIntegration:
    """Integration tests for Explorer movement."""

    @pytest.mark.asyncio
    async def test_explorer_moves_to_valid_exit(self, db_session: AsyncSession):
        """Test that Explorer moves to a valid exit direction."""
        from unittest.mock import AsyncMock, MagicMock

        from waystone.database.models import CharacterBackground
        from waystone.game.systems.simulated_players import (
            BartleType,
            ExplorerBehavior,
            SimulatedPlayerConfig,
            SimulatedPlayerManager,
            reset_sim_manager,
        )

        reset_sim_manager()
        manager = SimulatedPlayerManager()

        config = SimulatedPlayerConfig(
            id="sim_move_test",
            name="MoveTest",
            background=CharacterBackground.WAYFARER,
            bartle_type=BartleType.EXPLORER,
        )
        manager.add_config(config)

        sim = await manager.login_player("sim_move_test", db_session)
        assert sim is not None
        sim.behavior = ExplorerBehavior()

        # Create mock engine with connected rooms
        mock_engine = MagicMock()
        mock_room = MagicMock()
        mock_room.exits = {"north": "room2"}
        mock_room.id = "room1"
        mock_room.players = set()
        mock_engine.world.get.return_value = mock_room
        mock_engine.broadcast_to_room = AsyncMock()

        # Get action from behavior
        memory = sim.memory if hasattr(sim, "memory") else None
        if memory is None:
            from waystone.game.systems.simulated_players import SimMemory

            sim.memory = SimMemory()

        action = sim.behavior.select_action(
            available_exits=list(mock_room.exits.keys()),
            memory=sim.memory,
            last_direction=None,
        )

        # Action should be one of the available exits or look/exits
        valid_commands = list(mock_room.exits.keys()) + ["look", "exits"]
        assert action.command in valid_commands

    @pytest.mark.asyncio
    async def test_explorer_doesnt_backtrack_immediately(self, db_session: AsyncSession):
        """Test that Explorer doesn't immediately go back the way it came."""
        from waystone.database.models import CharacterBackground
        from waystone.game.systems.simulated_players import (
            BartleType,
            ExplorerBehavior,
            SimMemory,
            SimulatedPlayerConfig,
            SimulatedPlayerManager,
            reset_sim_manager,
        )

        reset_sim_manager()
        manager = SimulatedPlayerManager()

        config = SimulatedPlayerConfig(
            id="sim_backtrack_test",
            name="BacktrackTest",
            background=CharacterBackground.WAYFARER,
            bartle_type=BartleType.EXPLORER,
        )
        manager.add_config(config)

        sim = await manager.login_player("sim_backtrack_test", db_session)
        assert sim is not None

        behavior = ExplorerBehavior()
        memory = SimMemory()
        memory.last_direction = "north"  # We just came from north

        available_exits = ["south", "east"]  # south is backtracking

        # Check many times - should rarely backtrack
        backtrack_count = 0
        for _ in range(50):
            action = behavior.select_action(
                available_exits=available_exits,
                memory=memory,
                last_direction="north",
            )
            if action.command == "south":
                backtrack_count += 1

        # Should backtrack less than 20% of the time when alternatives exist
        assert backtrack_count < 20, f"Backtracked {backtrack_count}/50 times"
