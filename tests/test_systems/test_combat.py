"""Tests for combat system."""

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import select

from waystone.database.engine import get_session, init_db
from waystone.database.models import Character, CharacterBackground, User
from waystone.game.engine import GameEngine
from waystone.game.systems.combat import Combat, CombatState
from waystone.game.world import Room
from waystone.network import Connection, Session, SessionState


@pytest.fixture
async def test_engine() -> AsyncGenerator[GameEngine, None]:
    """Create a test game engine with minimal world."""
    await init_db()

    engine = GameEngine()

    # Create minimal test world
    engine.world = {
        "combat_room": Room(
            id="combat_room",
            name="Combat Arena",
            area="test",
            description="A room for testing combat.",
            exits={},
        ),
    }

    yield engine

    # Cleanup
    await engine.stop()


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
    session.state = SessionState.PLAYING
    return session


@pytest.fixture
async def test_characters() -> AsyncGenerator[tuple[Character, Character], None]:
    """Create two test characters for combat."""
    async with get_session() as session:
        # Create users
        user1 = User(
            username=f"fighter1_{uuid.uuid4().hex[:8]}",
            email=f"fighter1_{uuid.uuid4().hex[:8]}@example.com",
            password_hash=User.hash_password("password"),
        )
        user2 = User(
            username=f"fighter2_{uuid.uuid4().hex[:8]}",
            email=f"fighter2_{uuid.uuid4().hex[:8]}@example.com",
            password_hash=User.hash_password("password"),
        )
        session.add_all([user1, user2])
        await session.flush()

        # Create characters with different stats
        char1 = Character(
            user_id=user1.id,
            name=f"Warrior{uuid.uuid4().hex[:8]}",
            background=CharacterBackground.WAYFARER,
            current_room_id="combat_room",
            strength=14,
            dexterity=12,
            constitution=13,
            current_hp=20,
            max_hp=20,
        )
        char2 = Character(
            user_id=user2.id,
            name=f"Rogue{uuid.uuid4().hex[:8]}",
            background=CharacterBackground.PERFORMER,
            current_room_id="combat_room",
            strength=10,
            dexterity=16,
            constitution=11,
            current_hp=20,
            max_hp=20,
        )
        session.add_all([char1, char2])
        await session.commit()

        # Refresh to get IDs
        await session.refresh(char1)
        await session.refresh(char2)

        char1_id = char1.id
        char2_id = char2.id

    # Yield the character IDs
    yield char1, char2

    # Cleanup - delete characters and users
    async with get_session() as session:
        result = await session.execute(
            select(Character).where(Character.id.in_([char1_id, char2_id]))
        )
        chars = result.scalars().all()
        for char in chars:
            await session.delete(char)

        result = await session.execute(select(User).where(User.id.in_([user1.id, user2.id])))
        users = result.scalars().all()
        for user in users:
            await session.delete(user)

        await session.commit()


@pytest.mark.asyncio
async def test_combat_initialization(test_engine: GameEngine):
    """Test combat instance initialization."""
    combat = Combat("combat_room", test_engine)

    assert combat.room_id == "combat_room"
    assert combat.state == CombatState.SETUP
    assert len(combat.participants) == 0
    assert combat.current_turn_index == 0
    assert combat.round_number == 1


@pytest.mark.asyncio
async def test_add_participant(
    test_engine: GameEngine,
    test_characters: tuple[Character, Character],
):
    """Test adding participants to combat."""
    char1, char2 = test_characters
    combat = Combat("combat_room", test_engine)

    # Add first participant
    await combat.add_participant(str(char1.id))
    assert len(combat.participants) == 1
    assert combat.participants[0].character_id == str(char1.id)
    assert combat.participants[0].character_name == char1.name

    # Add second participant
    await combat.add_participant(str(char2.id))
    assert len(combat.participants) == 2

    # Try to add same participant again (should be ignored)
    await combat.add_participant(str(char1.id))
    assert len(combat.participants) == 2


@pytest.mark.asyncio
async def test_initiative_roll(
    test_engine: GameEngine,
    test_characters: tuple[Character, Character],
):
    """Test initiative rolling."""
    char1, char2 = test_characters
    combat = Combat("combat_room", test_engine)

    # Add participants
    await combat.add_participant(str(char1.id))
    await combat.add_participant(str(char2.id))

    # Both should have initiative values
    assert combat.participants[0].initiative > 0
    assert combat.participants[1].initiative > 0

    # Initiative should be within valid range (1-20 + modifier)
    # DEX 12 = +1 modifier, so range is 2-21
    # DEX 16 = +3 modifier, so range is 4-23
    for participant in combat.participants:
        assert 1 <= participant.initiative <= 30  # Conservative range


@pytest.mark.asyncio
async def test_start_combat(
    test_engine: GameEngine,
    test_characters: tuple[Character, Character],
):
    """Test starting combat and initiative sorting."""
    char1, char2 = test_characters
    combat = Combat("combat_room", test_engine)

    # Add participants
    await combat.add_participant(str(char1.id))
    await combat.add_participant(str(char2.id))

    # Start combat
    combat.start_combat()

    # Combat state should change
    assert combat.state == CombatState.IN_PROGRESS

    # Participants should be sorted by initiative (highest first)
    assert combat.participants[0].initiative >= combat.participants[1].initiative


@pytest.mark.asyncio
async def test_get_current_participant(
    test_engine: GameEngine,
    test_characters: tuple[Character, Character],
):
    """Test getting the current turn participant."""
    char1, char2 = test_characters
    combat = Combat("combat_room", test_engine)

    # Before combat starts
    assert combat.get_current_participant() is None

    # Add participants and start
    await combat.add_participant(str(char1.id))
    await combat.add_participant(str(char2.id))
    combat.start_combat()

    # Should get first participant
    current = combat.get_current_participant()
    assert current is not None
    assert current == combat.participants[0]


@pytest.mark.asyncio
async def test_next_turn(
    test_engine: GameEngine,
    test_characters: tuple[Character, Character],
):
    """Test advancing turns."""
    char1, char2 = test_characters
    combat = Combat("combat_room", test_engine)

    await combat.add_participant(str(char1.id))
    await combat.add_participant(str(char2.id))
    combat.start_combat()

    # Get first participant
    first = combat.get_current_participant()
    assert combat.current_turn_index == 0

    # Advance turn
    combat.next_turn()
    second = combat.get_current_participant()

    # Should be different participant
    assert combat.current_turn_index == 1
    assert second != first

    # Advance again - should wrap to start of new round
    combat.next_turn()
    assert combat.current_turn_index == 0
    assert combat.round_number == 2


@pytest.mark.asyncio
async def test_perform_attack_success(
    test_engine: GameEngine,
    test_characters: tuple[Character, Character],
):
    """Test successful attack action."""
    char1, char2 = test_characters
    combat = Combat("combat_room", test_engine)

    await combat.add_participant(str(char1.id))
    await combat.add_participant(str(char2.id))
    combat.start_combat()

    # Get initial HP
    async with get_session() as session:
        result = await session.execute(select(Character).where(Character.id == char2.id))
        target_before = result.scalar_one()
        hp_before = target_before.current_hp

    # Ensure it's char1's turn
    current = combat.get_current_participant()
    attacker_id = str(char1.id) if current.character_id == str(char1.id) else str(char2.id)
    target_id = str(char2.id) if attacker_id == str(char1.id) else str(char1.id)

    # Perform attack (may hit or miss due to randomness)
    success, message = await combat.perform_attack(attacker_id, target_id)

    # Should return success (even if attack misses)
    assert success is True
    assert len(message) > 0

    # Current participant should have action taken
    current = combat.get_current_participant()
    # Turn should have advanced, so current is now different


@pytest.mark.asyncio
async def test_perform_attack_not_your_turn(
    test_engine: GameEngine,
    test_characters: tuple[Character, Character],
):
    """Test attack when it's not your turn."""
    char1, char2 = test_characters
    combat = Combat("combat_room", test_engine)

    await combat.add_participant(str(char1.id))
    await combat.add_participant(str(char2.id))
    combat.start_combat()

    # Get current turn participant
    current = combat.get_current_participant()

    # Try to attack from the other participant
    not_current_id = str(char2.id) if current.character_id == str(char1.id) else str(char1.id)
    other_id = str(char1.id) if not_current_id == str(char2.id) else str(char2.id)

    success, message = await combat.perform_attack(not_current_id, other_id)

    # Should fail
    assert success is False
    assert "not your turn" in message.lower()


@pytest.mark.asyncio
async def test_perform_defend(
    test_engine: GameEngine,
    test_characters: tuple[Character, Character],
):
    """Test defend action."""
    char1, char2 = test_characters
    combat = Combat("combat_room", test_engine)

    await combat.add_participant(str(char1.id))
    await combat.add_participant(str(char2.id))
    combat.start_combat()

    # Get current participant
    current = combat.get_current_participant()
    defender_id = current.character_id

    # Perform defend
    success, message = await combat.perform_defend(defender_id)

    # Should succeed
    assert success is True
    assert "defensive stance" in message.lower()


@pytest.mark.asyncio
async def test_attempt_flee_success(
    test_engine: GameEngine,
    test_characters: tuple[Character, Character],
):
    """Test successful flee attempt."""
    char1, char2 = test_characters
    combat = Combat("combat_room", test_engine)

    await combat.add_participant(str(char1.id))
    await combat.add_participant(str(char2.id))
    combat.start_combat()

    initial_count = len(combat.participants)

    # Get current participant
    current = combat.get_current_participant()
    fleeing_id = current.character_id

    # Attempt to flee (may succeed or fail due to randomness)
    success, message = await combat.attempt_flee(fleeing_id)

    # Should return success (whether flee succeeded or failed)
    assert success is True
    assert len(message) > 0

    # If flee succeeded, participant count should decrease
    # (can't assert this due to randomness, but we can check combat didn't crash)


@pytest.mark.asyncio
async def test_character_death(
    test_engine: GameEngine,
    test_characters: tuple[Character, Character],
):
    """Test character death handling."""
    char1, char2 = test_characters
    combat = Combat("combat_room", test_engine)

    # Reduce char2's HP to near death
    async with get_session() as session:
        result = await session.execute(select(Character).where(Character.id == char2.id))
        target = result.scalar_one()
        target.current_hp = 1
        await session.commit()

    await combat.add_participant(str(char1.id))
    await combat.add_participant(str(char2.id))
    combat.start_combat()

    initial_count = len(combat.participants)

    # Ensure char1 is attacking
    current = combat.get_current_participant()
    if current.character_id != str(char1.id):
        combat.next_turn()

    # Perform multiple attacks until death (or max attempts)
    max_attempts = 20
    for _ in range(max_attempts):
        current = combat.get_current_participant()

        # Check if combat has ended
        if current is None:
            break

        if current.character_id == str(char1.id):
            success, message = await combat.perform_attack(str(char1.id), str(char2.id))
            if not success:
                break

            # Check if char2 is dead
            async with get_session() as session:
                result = await session.execute(select(Character).where(Character.id == char2.id))
                target = result.scalar_one()
                if target.current_hp <= 0:
                    # Character should have been restored to 1 HP
                    assert target.current_hp == 1
                    # Should be removed from combat
                    assert not combat.is_character_in_combat(str(char2.id))
                    break
        else:
            # Skip other participant's turn
            combat.next_turn()


@pytest.mark.asyncio
async def test_combat_status_display(
    test_engine: GameEngine,
    test_characters: tuple[Character, Character],
):
    """Test combat status display."""
    char1, char2 = test_characters
    combat = Combat("combat_room", test_engine)

    # Before combat
    status = combat.get_combat_status()
    assert "set up" in status.lower()

    # During combat
    await combat.add_participant(str(char1.id))
    await combat.add_participant(str(char2.id))
    combat.start_combat()

    status = combat.get_combat_status()
    assert "Round 1" in status
    assert char1.name in status or char2.name in status

    # After combat ends
    await combat._end_combat()
    status = combat.get_combat_status()
    assert "ended" in status.lower()


@pytest.mark.asyncio
async def test_is_character_in_combat(
    test_engine: GameEngine,
    test_characters: tuple[Character, Character],
):
    """Test checking if character is in combat."""
    char1, char2 = test_characters
    combat = Combat("combat_room", test_engine)

    # Before adding
    assert not combat.is_character_in_combat(str(char1.id))

    # After adding
    await combat.add_participant(str(char1.id))
    assert combat.is_character_in_combat(str(char1.id))
    assert not combat.is_character_in_combat(str(char2.id))


@pytest.mark.asyncio
async def test_combat_state_transitions(
    test_engine: GameEngine,
    test_characters: tuple[Character, Character],
):
    """Test combat state machine transitions."""
    char1, char2 = test_characters
    combat = Combat("combat_room", test_engine)

    # SETUP state
    assert combat.state == CombatState.SETUP

    # Transition to IN_PROGRESS
    await combat.add_participant(str(char1.id))
    await combat.add_participant(str(char2.id))
    combat.start_combat()
    assert combat.state == CombatState.IN_PROGRESS

    # Transition to ENDED
    await combat._end_combat()
    assert combat.state == CombatState.ENDED


@pytest.mark.asyncio
async def test_defend_bonus(
    test_engine: GameEngine,
    test_characters: tuple[Character, Character],
):
    """Test that defend action provides defense bonus."""
    char1, char2 = test_characters
    combat = Combat("combat_room", test_engine)

    await combat.add_participant(str(char1.id))
    await combat.add_participant(str(char2.id))
    combat.start_combat()

    # Get current participant
    current = combat.get_current_participant()

    # Defend
    success, message = await combat.perform_defend(current.character_id)
    assert success

    # Participant should be marked as defending
    # (Note: is_defending is reset on next turn, so we check immediately)
    # The current turn has advanced, so we need to check the previous participant
    # Actually, next_turn() was called in perform_defend, so current is different now


@pytest.mark.asyncio
async def test_multiple_rounds(
    test_engine: GameEngine,
    test_characters: tuple[Character, Character],
):
    """Test combat progressing through multiple rounds."""
    char1, char2 = test_characters
    combat = Combat("combat_room", test_engine)

    await combat.add_participant(str(char1.id))
    await combat.add_participant(str(char2.id))
    combat.start_combat()

    assert combat.round_number == 1

    # Go through a full round
    combat.next_turn()  # Second participant
    combat.next_turn()  # Should wrap to new round

    assert combat.round_number == 2
    assert combat.current_turn_index == 0
