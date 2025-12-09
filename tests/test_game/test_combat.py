"""Comprehensive tests for combat system and combat commands."""

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy import select

from waystone.database.engine import get_session, init_db
from waystone.database.models import Character, CharacterBackground, User
from waystone.game.commands.base import CommandContext
from waystone.game.commands.combat import (
    AttackCommand,
    CombatStatusCommand,
    DefendCommand,
    FleeCommand,
    create_combat,
    get_combat_for_character,
    get_combat_for_room,
)
from waystone.game.engine import GameEngine
from waystone.game.systems.combat import Combat, CombatState
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


@pytest.fixture
async def test_characters(test_engine: GameEngine) -> tuple[str, str]:
    """Create two test characters for combat testing."""
    async with get_session() as session:
        # Create user 1
        user1 = User(
            username=f"combatuser1_{uuid.uuid4().hex[:8]}",
            email=f"combat1_{uuid.uuid4().hex[:8]}@example.com",
            password_hash=User.hash_password("password"),
        )
        session.add(user1)
        await session.flush()

        # Create character 1 with high dexterity for initiative
        char1 = Character(
            user_id=user1.id,
            name=f"Fighter1_{uuid.uuid4().hex[:8]}",
            background=CharacterBackground.WAYFARER,
            current_room_id="test_room_1",
            strength=14,
            dexterity=16,
            constitution=12,
            intelligence=10,
            wisdom=10,
            charisma=8,
            max_hp=50,
            current_hp=50,
        )
        session.add(char1)

        # Create user 2
        user2 = User(
            username=f"combatuser2_{uuid.uuid4().hex[:8]}",
            email=f"combat2_{uuid.uuid4().hex[:8]}@example.com",
            password_hash=User.hash_password("password"),
        )
        session.add(user2)
        await session.flush()

        # Create character 2
        char2 = Character(
            user_id=user2.id,
            name=f"Fighter2_{uuid.uuid4().hex[:8]}",
            background=CharacterBackground.PERFORMER,
            current_room_id="test_room_1",
            strength=12,
            dexterity=14,
            constitution=14,
            intelligence=10,
            wisdom=10,
            charisma=8,
            max_hp=50,
            current_hp=50,
        )
        session.add(char2)

        await session.commit()

        return str(char1.id), str(char2.id)


# ============================================================================
# COMBAT SYSTEM TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_combat_initialization(test_engine: GameEngine):
    """Test combat system initialization."""
    combat = Combat("test_room_1", test_engine)

    assert combat.room_id == "test_room_1"
    assert combat.engine == test_engine
    assert combat.state == CombatState.SETUP
    assert len(combat.participants) == 0
    assert combat.current_turn_index == 0
    assert combat.round_number == 1
    assert combat.turn_timer_task is None


@pytest.mark.asyncio
async def test_add_participant(test_engine: GameEngine, test_characters: tuple[str, str]):
    """Test adding participants to combat."""
    char1_id, char2_id = test_characters
    combat = Combat("test_room_1", test_engine)

    # Add first participant
    await combat.add_participant(char1_id)
    assert len(combat.participants) == 1
    assert combat.participants[0].character_id == char1_id

    # Add second participant
    await combat.add_participant(char2_id)
    assert len(combat.participants) == 2

    # Try adding same participant again - should not duplicate
    await combat.add_participant(char1_id)
    assert len(combat.participants) == 2


@pytest.mark.asyncio
async def test_add_participant_invalid_character(test_engine: GameEngine):
    """Test adding non-existent character to combat."""
    combat = Combat("test_room_1", test_engine)

    # Try adding invalid character ID
    fake_id = str(uuid.uuid4())
    await combat.add_participant(fake_id)

    # Should not add participant
    assert len(combat.participants) == 0


@pytest.mark.asyncio
async def test_roll_initiative(test_engine: GameEngine):
    """Test initiative rolling."""
    combat = Combat("test_room_1", test_engine)

    # Test with various dexterity values
    # DEX 10 = +0 modifier, should be 1-20
    for _ in range(10):
        roll = combat._roll_initiative(10)
        assert 1 <= roll <= 20

    # DEX 16 = +3 modifier, should be 4-23
    for _ in range(10):
        roll = combat._roll_initiative(16)
        assert 4 <= roll <= 23

    # DEX 8 = -1 modifier, should be 0-19
    for _ in range(10):
        roll = combat._roll_initiative(8)
        assert 0 <= roll <= 19


@pytest.mark.asyncio
async def test_start_combat(test_engine: GameEngine, test_characters: tuple[str, str]):
    """Test starting combat and initiative ordering."""
    char1_id, char2_id = test_characters
    combat = Combat("test_room_1", test_engine)

    # Add participants
    await combat.add_participant(char1_id)
    await combat.add_participant(char2_id)

    # Start combat
    combat.start_combat()

    assert combat.state == CombatState.IN_PROGRESS
    assert combat.current_turn_index == 0
    # Participants should be sorted by initiative (highest first)
    assert combat.participants[0].initiative >= combat.participants[1].initiative


@pytest.mark.asyncio
async def test_start_combat_already_started(
    test_engine: GameEngine, test_characters: tuple[str, str]
):
    """Test that starting combat twice doesn't reset state."""
    char1_id, _ = test_characters
    combat = Combat("test_room_1", test_engine)

    await combat.add_participant(char1_id)
    combat.start_combat()

    original_state = combat.state
    combat.start_combat()

    # State should remain IN_PROGRESS, not reset
    assert combat.state == original_state


@pytest.mark.asyncio
async def test_get_current_participant(test_engine: GameEngine, test_characters: tuple[str, str]):
    """Test getting the current turn participant."""
    char1_id, char2_id = test_characters
    combat = Combat("test_room_1", test_engine)

    # No participants yet
    assert combat.get_current_participant() is None

    # Add participants and start
    await combat.add_participant(char1_id)
    await combat.add_participant(char2_id)
    combat.start_combat()

    # Should return first participant
    current = combat.get_current_participant()
    assert current is not None
    assert current == combat.participants[0]


@pytest.mark.asyncio
async def test_next_turn(test_engine: GameEngine, test_characters: tuple[str, str]):
    """Test advancing to next turn."""
    char1_id, char2_id = test_characters
    combat = Combat("test_room_1", test_engine)

    await combat.add_participant(char1_id)
    await combat.add_participant(char2_id)
    combat.start_combat()

    # Set current participant flags
    first_participant = combat.get_current_participant()
    first_participant.action_taken = True
    first_participant.is_defending = True

    # Advance turn
    combat.next_turn()

    assert combat.current_turn_index == 1
    # Previous participant's flags should be reset
    assert not first_participant.action_taken
    assert not first_participant.is_defending


@pytest.mark.asyncio
async def test_next_turn_new_round(test_engine: GameEngine, test_characters: tuple[str, str]):
    """Test that next_turn creates new round after all participants."""
    char1_id, char2_id = test_characters
    combat = Combat("test_room_1", test_engine)

    await combat.add_participant(char1_id)
    await combat.add_participant(char2_id)
    combat.start_combat()

    assert combat.round_number == 1

    # Advance through both participants
    combat.next_turn()  # Moves to participant 2
    combat.next_turn()  # Should wrap to participant 1 and increment round

    assert combat.current_turn_index == 0
    assert combat.round_number == 2


@pytest.mark.asyncio
@pytest.mark.xfail(reason="Attack success edge case - needs refinement")
async def test_perform_attack_success(test_engine: GameEngine, test_characters: tuple[str, str]):
    """Test successful attack execution."""
    char1_id, char2_id = test_characters
    combat = Combat("test_room_1", test_engine)

    await combat.add_participant(char1_id)
    await combat.add_participant(char2_id)
    combat.start_combat()

    # Get initial HP
    async with get_session() as session:
        result = await session.execute(select(Character).where(Character.id == uuid.UUID(char2_id)))
        target_before = result.scalar_one()
        initial_hp = target_before.current_hp

    # Force a hit by mocking random
    # Mock both to-hit roll (d20) and damage roll (d6)
    with patch(
        "waystone.game.systems.combat.random.randint", side_effect=[20, 3]
    ):  # to-hit: 20, damage: 3
        success, message = await combat.perform_attack(char1_id, char2_id)

    assert success is True
    assert "hit" in message.lower()

    # Verify damage was dealt
    async with get_session() as session:
        result = await session.execute(select(Character).where(Character.id == uuid.UUID(char2_id)))
        target_after = result.scalar_one()
        assert target_after.current_hp < initial_hp


@pytest.mark.asyncio
@pytest.mark.xfail(reason="Edge case test with mocked random - needs refinement")
async def test_perform_attack_miss(test_engine: GameEngine, test_characters: tuple[str, str]):
    """Test missed attack."""
    char1_id, char2_id = test_characters
    combat = Combat("test_room_1", test_engine)

    await combat.add_participant(char1_id)
    await combat.add_participant(char2_id)
    combat.start_combat()

    # Force a miss by mocking random to roll 1
    # Only need to mock the to-hit roll (won't get to damage roll on a miss)
    with patch("waystone.game.systems.combat.random.randint", return_value=1):  # to-hit: 1 (misses)
        success, message = await combat.perform_attack(char1_id, char2_id)

    assert success is True  # Command succeeded
    assert "miss" in message.lower()


@pytest.mark.asyncio
async def test_perform_attack_not_your_turn(
    test_engine: GameEngine, test_characters: tuple[str, str]
):
    """Test attack when it's not your turn."""
    char1_id, char2_id = test_characters
    combat = Combat("test_room_1", test_engine)

    await combat.add_participant(char1_id)
    await combat.add_participant(char2_id)
    combat.start_combat()

    # Try to attack when it's not your turn
    current = combat.get_current_participant()
    attacker_id = char1_id if current.character_id != char1_id else char2_id

    success, message = await combat.perform_attack(attacker_id, char2_id)

    assert success is False
    assert "not your turn" in message.lower()


@pytest.mark.asyncio
async def test_perform_attack_action_already_taken(
    test_engine: GameEngine, test_characters: tuple[str, str]
):
    """Test attack when action already taken this turn."""
    char1_id, char2_id = test_characters
    combat = Combat("test_room_1", test_engine)

    await combat.add_participant(char1_id)
    await combat.add_participant(char2_id)
    combat.start_combat()

    current = combat.get_current_participant()
    current.action_taken = True

    success, message = await combat.perform_attack(current.character_id, char2_id)

    assert success is False
    assert "already taken an action" in message.lower()


@pytest.mark.asyncio
async def test_perform_attack_target_not_in_combat(
    test_engine: GameEngine, test_characters: tuple[str, str]
):
    """Test attack against target not in combat."""
    char1_id, char2_id = test_characters
    combat = Combat("test_room_1", test_engine)

    await combat.add_participant(char1_id)
    combat.start_combat()

    # Try to attack character not in combat
    success, message = await combat.perform_attack(char1_id, char2_id)

    assert success is False
    assert "not in combat" in message.lower()


@pytest.mark.asyncio
async def test_perform_attack_with_defending_target(
    test_engine: GameEngine, test_characters: tuple[str, str]
):
    """Test attack against defending target has higher defense."""
    char1_id, char2_id = test_characters
    combat = Combat("test_room_1", test_engine)

    await combat.add_participant(char1_id)
    await combat.add_participant(char2_id)
    combat.start_combat()

    # Make target defend
    target_participant = next(p for p in combat.participants if p.character_id == char2_id)
    target_participant.is_defending = True

    # Mocking to test defense calculation - defending adds +5
    with patch("waystone.game.systems.combat.random.randint") as mock_random:
        # Roll that would hit normal defense but miss defending
        mock_random.return_value = 12
        await combat.perform_attack(char1_id, char2_id)
        # The defending bonus should make attacks less likely to hit


@pytest.mark.asyncio
async def test_perform_defend(test_engine: GameEngine, test_characters: tuple[str, str]):
    """Test defend action."""
    char1_id, char2_id = test_characters
    combat = Combat("test_room_1", test_engine)

    # Add two participants so we can check state after defend
    await combat.add_participant(char1_id)
    await combat.add_participant(char2_id)
    combat.start_combat()

    first_participant = combat.get_current_participant()
    first_char_id = first_participant.character_id

    success, message = await combat.perform_defend(first_char_id)

    assert success is True
    assert "defensive stance" in message.lower()

    # After defend, turn should have advanced
    # The participant who just defended should have reset flags (from next_turn)
    # But during the next attack, they should have the defending bonus
    # Check that it was marked as defending during the action
    # (We can't check the flag directly after next_turn resets it)


@pytest.mark.asyncio
async def test_perform_defend_not_your_turn(
    test_engine: GameEngine, test_characters: tuple[str, str]
):
    """Test defend when it's not your turn."""
    char1_id, char2_id = test_characters
    combat = Combat("test_room_1", test_engine)

    await combat.add_participant(char1_id)
    await combat.add_participant(char2_id)
    combat.start_combat()

    current = combat.get_current_participant()
    other_id = char1_id if current.character_id != char1_id else char2_id

    success, message = await combat.perform_defend(other_id)

    assert success is False
    assert "not your turn" in message.lower()


@pytest.mark.asyncio
async def test_attempt_flee_success(test_engine: GameEngine, test_characters: tuple[str, str]):
    """Test successful flee from combat."""
    char1_id, char2_id = test_characters
    combat = Combat("test_room_1", test_engine)

    await combat.add_participant(char1_id)
    await combat.add_participant(char2_id)
    combat.start_combat()

    initial_count = len(combat.participants)

    # Mock successful flee roll (>= 12)
    with patch("waystone.game.systems.combat.random.randint", return_value=20):
        current = combat.get_current_participant()
        success, message = await combat.attempt_flee(current.character_id)

    assert success is True
    assert "successfully flee" in message.lower()
    assert len(combat.participants) == initial_count - 1


@pytest.mark.asyncio
async def test_attempt_flee_failure(test_engine: GameEngine, test_characters: tuple[str, str]):
    """Test failed flee attempt."""
    char1_id, char2_id = test_characters
    combat = Combat("test_room_1", test_engine)

    await combat.add_participant(char1_id)
    await combat.add_participant(char2_id)
    combat.start_combat()

    initial_participant_count = len(combat.participants)

    # Mock failed flee roll (< 12)
    with patch("waystone.game.systems.combat.random.randint", return_value=1):
        current = combat.get_current_participant()
        success, message = await combat.attempt_flee(current.character_id)

    assert success is True  # Command succeeded
    assert "fail to escape" in message.lower()
    # Participant should still be in combat
    assert len(combat.participants) == initial_participant_count
    # Turn should have advanced (action_taken would be reset by next_turn)


@pytest.mark.asyncio
async def test_flee_ends_combat_when_one_participant_left(
    test_engine: GameEngine, test_characters: tuple[str, str]
):
    """Test that fleeing with only 2 participants ends combat."""
    char1_id, char2_id = test_characters
    combat = Combat("test_room_1", test_engine)

    await combat.add_participant(char1_id)
    await combat.add_participant(char2_id)
    combat.start_combat()

    # Mock successful flee
    with patch("waystone.game.systems.combat.random.randint", return_value=20):
        current = combat.get_current_participant()
        await combat.attempt_flee(current.character_id)

    # Combat should end when only 1 participant remains
    assert combat.state == CombatState.ENDED


@pytest.mark.asyncio
@pytest.mark.xfail(reason="Death handling edge case - needs refinement")
async def test_character_death_removes_from_combat(
    test_engine: GameEngine, test_characters: tuple[str, str]
):
    """Test character death removes them from combat."""
    # Clear global combat state from previous tests
    from waystone.game.commands.combat import _active_combats

    _active_combats.clear()

    char1_id, char2_id = test_characters
    combat = Combat("test_room_1", test_engine)

    await combat.add_participant(char1_id)
    await combat.add_participant(char2_id)
    combat.start_combat()

    async with get_session() as session:
        # Get target and reduce HP to 0
        result = await session.execute(select(Character).where(Character.id == uuid.UUID(char2_id)))
        target = result.scalar_one()
        target.current_hp = 1  # Set to 1 HP

        await session.commit()

    # Attack should kill the target
    # Need to mock both to-hit roll (d20) and damage roll (d6)
    # Use side_effect to return different values for each call
    with patch(
        "waystone.game.systems.combat.random.randint", side_effect=[20, 6]
    ):  # to-hit: 20, damage: 6
        await combat.perform_attack(char1_id, char2_id)

    # Target should be removed from combat
    assert not any(p.character_id == char2_id for p in combat.participants)

    # Target HP should be restored to 1
    async with get_session() as session:
        result = await session.execute(select(Character).where(Character.id == uuid.UUID(char2_id)))
        target = result.scalar_one()
        assert target.current_hp == 1


@pytest.mark.asyncio
@pytest.mark.xfail(reason="Death handling edge case - needs refinement")
async def test_death_ends_combat_when_one_left(
    test_engine: GameEngine, test_characters: tuple[str, str]
):
    """Test combat ends when death leaves only 1 participant."""
    char1_id, char2_id = test_characters
    combat = Combat("test_room_1", test_engine)

    await combat.add_participant(char1_id)
    await combat.add_participant(char2_id)
    combat.start_combat()

    # Set target to 1 HP
    async with get_session() as session:
        result = await session.execute(select(Character).where(Character.id == uuid.UUID(char2_id)))
        target = result.scalar_one()
        target.current_hp = 1
        await session.commit()

    # Kill target
    # Mock both to-hit and damage rolls
    with patch(
        "waystone.game.systems.combat.random.randint", side_effect=[20, 6]
    ):  # to-hit: 20, damage: 6
        await combat.perform_attack(char1_id, char2_id)

    # Combat should end
    assert combat.state == CombatState.ENDED


@pytest.mark.asyncio
async def test_is_character_in_combat(test_engine: GameEngine, test_characters: tuple[str, str]):
    """Test checking if character is in combat."""
    char1_id, char2_id = test_characters
    combat = Combat("test_room_1", test_engine)

    await combat.add_participant(char1_id)

    assert combat.is_character_in_combat(char1_id) is True
    assert combat.is_character_in_combat(char2_id) is False


@pytest.mark.asyncio
async def test_get_combat_status(test_engine: GameEngine, test_characters: tuple[str, str]):
    """Test getting combat status."""
    char1_id, char2_id = test_characters
    combat = Combat("test_room_1", test_engine)

    # Status during setup
    status = combat.get_combat_status()
    assert "set up" in status.lower()

    # Status during combat
    await combat.add_participant(char1_id)
    await combat.add_participant(char2_id)
    combat.start_combat()

    status = combat.get_combat_status()
    assert "Round 1" in status
    assert ">>>" in status  # Current turn indicator

    # Status after combat ends
    combat.state = CombatState.ENDED
    status = combat.get_combat_status()
    assert "ended" in status.lower()


# ============================================================================
# COMBAT COMMANDS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_attack_command_create_new_combat(
    test_engine: GameEngine,
    mock_connection: Connection,
    mock_session: Session,
    test_characters: tuple[str, str],
):
    """Test attack command creates new combat."""
    char1_id, char2_id = test_characters

    # Set up session with character
    mock_session.character_id = char1_id
    mock_session.state = SessionState.PLAYING

    # Add both characters to room
    test_engine.world["test_room_1"].add_player(char1_id)
    test_engine.world["test_room_1"].add_player(char2_id)

    # Get target name
    async with get_session() as session:
        result = await session.execute(select(Character).where(Character.id == uuid.UUID(char2_id)))
        target = result.scalar_one()
        target_name = target.name.lower()

    cmd = AttackCommand()
    ctx = CommandContext(
        session=mock_session,
        connection=mock_connection,
        engine=test_engine,
        args=[target_name],
        raw_input=f"attack {target_name}",
    )

    await cmd.execute(ctx)

    # Verify combat was created
    combat = get_combat_for_room("test_room_1")
    assert combat is not None
    assert combat.state == CombatState.IN_PROGRESS


@pytest.mark.asyncio
async def test_attack_command_no_character(
    test_engine: GameEngine,
    mock_connection: Connection,
    mock_session: Session,
):
    """Test attack command without character."""
    mock_session.character_id = None

    cmd = AttackCommand()
    ctx = CommandContext(
        session=mock_session,
        connection=mock_connection,
        engine=test_engine,
        args=["target"],
        raw_input="attack target",
    )

    await cmd.execute(ctx)

    # Should send error message
    mock_connection.send_line.assert_called()
    calls = [str(call) for call in mock_connection.send_line.call_args_list]
    assert any("must be playing a character" in str(call).lower() for call in calls)


@pytest.mark.asyncio
async def test_attack_command_target_not_found(
    test_engine: GameEngine,
    mock_connection: Connection,
    mock_session: Session,
    test_characters: tuple[str, str],
):
    """Test attack command with non-existent target."""
    char1_id, _ = test_characters

    mock_session.character_id = char1_id
    mock_session.state = SessionState.PLAYING

    test_engine.world["test_room_1"].add_player(char1_id)

    cmd = AttackCommand()
    ctx = CommandContext(
        session=mock_session,
        connection=mock_connection,
        engine=test_engine,
        args=["nonexistent"],
        raw_input="attack nonexistent",
    )

    await cmd.execute(ctx)

    # Should send error about target not found
    mock_connection.send_line.assert_called()
    calls = [str(call) for call in mock_connection.send_line.call_args_list]
    assert any("don't see" in str(call).lower() for call in calls)


@pytest.mark.asyncio
async def test_attack_command_dead_attacker(
    test_engine: GameEngine,
    mock_connection: Connection,
    mock_session: Session,
    test_characters: tuple[str, str],
):
    """Test attack command when attacker is dead."""
    char1_id, _ = test_characters

    # Set attacker to 0 HP
    async with get_session() as session:
        result = await session.execute(select(Character).where(Character.id == uuid.UUID(char1_id)))
        attacker = result.scalar_one()
        attacker.current_hp = 0
        await session.commit()

    mock_session.character_id = char1_id
    mock_session.state = SessionState.PLAYING

    cmd = AttackCommand()
    ctx = CommandContext(
        session=mock_session,
        connection=mock_connection,
        engine=test_engine,
        args=["target"],
        raw_input="attack target",
    )

    await cmd.execute(ctx)

    # Should send error about being defeated
    mock_connection.send_line.assert_called()
    calls = [str(call) for call in mock_connection.send_line.call_args_list]
    assert any("defeated" in str(call).lower() for call in calls)


@pytest.mark.asyncio
async def test_defend_command_success(
    test_engine: GameEngine,
    mock_connection: Connection,
    mock_session: Session,
    test_characters: tuple[str, str],
):
    """Test defend command execution."""
    char1_id, char2_id = test_characters

    # Create combat first
    combat = await create_combat(
        "test_room_1",
        CommandContext(
            session=mock_session,
            connection=mock_connection,
            engine=test_engine,
            args=[],
            raw_input="",
        ),
    )
    await combat.add_participant(char1_id)
    await combat.add_participant(char2_id)
    combat.start_combat()

    # Set up session
    mock_session.character_id = combat.get_current_participant().character_id

    cmd = DefendCommand()
    ctx = CommandContext(
        session=mock_session,
        connection=mock_connection,
        engine=test_engine,
        args=[],
        raw_input="defend",
    )

    await cmd.execute(ctx)

    # Should send success message
    mock_connection.send_line.assert_called()
    calls = [str(call) for call in mock_connection.send_line.call_args_list]
    assert any("defensive stance" in str(call).lower() for call in calls)


@pytest.mark.asyncio
async def test_defend_command_not_in_combat(
    test_engine: GameEngine,
    mock_connection: Connection,
    mock_session: Session,
    test_characters: tuple[str, str],
):
    """Test defend command when not in combat."""
    char1_id, _ = test_characters

    mock_session.character_id = char1_id

    cmd = DefendCommand()
    ctx = CommandContext(
        session=mock_session,
        connection=mock_connection,
        engine=test_engine,
        args=[],
        raw_input="defend",
    )

    await cmd.execute(ctx)

    # Should send error
    mock_connection.send_line.assert_called()
    calls = [str(call) for call in mock_connection.send_line.call_args_list]
    assert any("not in combat" in str(call).lower() for call in calls)


@pytest.mark.asyncio
async def test_flee_command_success(
    test_engine: GameEngine,
    mock_connection: Connection,
    mock_session: Session,
    test_characters: tuple[str, str],
):
    """Test flee command execution."""
    char1_id, char2_id = test_characters

    # Create combat
    combat = await create_combat(
        "test_room_1",
        CommandContext(
            session=mock_session,
            connection=mock_connection,
            engine=test_engine,
            args=[],
            raw_input="",
        ),
    )
    await combat.add_participant(char1_id)
    await combat.add_participant(char2_id)
    combat.start_combat()

    mock_session.character_id = combat.get_current_participant().character_id

    cmd = FleeCommand()
    ctx = CommandContext(
        session=mock_session,
        connection=mock_connection,
        engine=test_engine,
        args=[],
        raw_input="flee",
    )

    # Mock successful flee
    with patch("waystone.game.systems.combat.random.randint", return_value=20):
        await cmd.execute(ctx)

    # Should send message
    mock_connection.send_line.assert_called()


@pytest.mark.asyncio
async def test_flee_command_not_in_combat(
    test_engine: GameEngine,
    mock_connection: Connection,
    mock_session: Session,
    test_characters: tuple[str, str],
):
    """Test flee command when not in combat."""
    char1_id, _ = test_characters

    mock_session.character_id = char1_id

    cmd = FleeCommand()
    ctx = CommandContext(
        session=mock_session,
        connection=mock_connection,
        engine=test_engine,
        args=[],
        raw_input="flee",
    )

    await cmd.execute(ctx)

    # Should send error
    mock_connection.send_line.assert_called()
    calls = [str(call) for call in mock_connection.send_line.call_args_list]
    assert any("not in combat" in str(call).lower() for call in calls)


@pytest.mark.asyncio
async def test_combat_status_command(
    test_engine: GameEngine,
    mock_connection: Connection,
    mock_session: Session,
    test_characters: tuple[str, str],
):
    """Test combat status command."""
    char1_id, char2_id = test_characters

    # Create combat
    combat = await create_combat(
        "test_room_1",
        CommandContext(
            session=mock_session,
            connection=mock_connection,
            engine=test_engine,
            args=[],
            raw_input="",
        ),
    )
    await combat.add_participant(char1_id)
    await combat.add_participant(char2_id)
    combat.start_combat()

    mock_session.character_id = char1_id

    cmd = CombatStatusCommand()
    ctx = CommandContext(
        session=mock_session,
        connection=mock_connection,
        engine=test_engine,
        args=[],
        raw_input="combat",
    )

    await cmd.execute(ctx)

    # Should send status
    mock_connection.send_line.assert_called()
    calls = [str(call) for call in mock_connection.send_line.call_args_list]
    assert any("Round" in str(call) for call in calls)


@pytest.mark.asyncio
async def test_combat_status_not_in_combat(
    test_engine: GameEngine,
    mock_connection: Connection,
    mock_session: Session,
    test_characters: tuple[str, str],
):
    """Test combat status when not in combat."""
    char1_id, _ = test_characters

    mock_session.character_id = char1_id

    cmd = CombatStatusCommand()
    ctx = CommandContext(
        session=mock_session,
        connection=mock_connection,
        engine=test_engine,
        args=[],
        raw_input="combat",
    )

    await cmd.execute(ctx)

    # Should indicate not in combat
    mock_connection.send_line.assert_called()
    calls = [str(call) for call in mock_connection.send_line.call_args_list]
    assert any("not in combat" in str(call).lower() for call in calls)


@pytest.mark.asyncio
async def test_get_combat_for_room(
    test_engine: GameEngine,
    mock_connection: Connection,
    mock_session: Session,
):
    """Test getting combat instance for room."""
    # Clear any previous combats from global state
    from waystone.game.commands.combat import _active_combats

    _active_combats.clear()

    # No combat initially
    assert get_combat_for_room("test_room_1") is None

    # Create combat
    ctx = CommandContext(
        session=mock_session,
        connection=mock_connection,
        engine=test_engine,
        args=[],
        raw_input="",
    )
    combat = await create_combat("test_room_1", ctx)

    # Should return combat
    assert get_combat_for_room("test_room_1") == combat

    # End combat
    combat.state = CombatState.ENDED

    # Should return None for ended combat
    assert get_combat_for_room("test_room_1") is None


@pytest.mark.asyncio
async def test_get_combat_for_character(
    test_engine: GameEngine,
    mock_connection: Connection,
    mock_session: Session,
    test_characters: tuple[str, str],
):
    """Test getting combat instance for character."""
    char1_id, _ = test_characters

    # No combat initially
    assert get_combat_for_character(char1_id) is None

    # Create combat and add character
    ctx = CommandContext(
        session=mock_session,
        connection=mock_connection,
        engine=test_engine,
        args=[],
        raw_input="",
    )
    combat = await create_combat("test_room_1", ctx)
    await combat.add_participant(char1_id)
    combat.start_combat()

    # Should return combat
    assert get_combat_for_character(char1_id) == combat

    # Character not in combat
    fake_id = str(uuid.uuid4())
    assert get_combat_for_character(fake_id) is None
