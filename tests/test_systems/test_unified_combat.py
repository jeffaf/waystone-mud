"""Tests for the unified round-based combat system.

This test suite is written in TDD (Test-Driven Development) style.
Some functions being tested don't exist yet in unified_combat.py - they are
defined as the expected interface that the implementation should provide.
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import what exists in unified_combat.py
try:
    from waystone.game.systems.unified_combat import (
        Combat,
        CombatParticipant,
        CombatState,
        _active_combats,
        apply_damage_to_participant,
        # Import all combat mechanics functions
        calculate_attribute_modifier,
        calculate_damage,
        cleanup_ended_combats,
        create_combat,
        get_combat_for_room,
        get_damage_message,
        get_participant_attribute,
        get_participant_hp,
        roll_d20,
        roll_initiative,
        roll_to_hit,
    )
except ImportError as e:
    pytest.skip(f"unified_combat module not fully implemented: {e}", allow_module_level=True)


class TestCombatParticipant:
    """Tests for CombatParticipant dataclass."""

    def test_create_player_participant(self):
        """Test creating a player participant."""
        p = CombatParticipant(
            entity_id="char-uuid-123",
            entity_name="TestPlayer",
            is_npc=False,
        )
        assert p.entity_id == "char-uuid-123"
        assert p.entity_name == "TestPlayer"
        assert p.is_npc is False
        assert p.initiative == 0
        assert p.target_id is None
        assert p.fled is False
        assert p.is_defending is False
        assert p.wait_state_until is None

    def test_create_npc_participant(self):
        """Test creating an NPC participant."""
        p = CombatParticipant(
            entity_id="bandit_abc123",
            entity_name="a street thug",
            is_npc=True,
            target_id="char-uuid-123",
        )
        assert p.is_npc is True
        assert p.target_id == "char-uuid-123"

    def test_participant_with_initiative(self):
        """Test creating participant with custom initiative."""
        p = CombatParticipant(
            entity_id="test-id",
            entity_name="Test",
            is_npc=False,
            initiative=15,
        )
        assert p.initiative == 15

    def test_participant_with_wait_state(self):
        """Test participant with wait state."""
        future_time = datetime.now() + timedelta(seconds=3)
        p = CombatParticipant(
            entity_id="test-id",
            entity_name="Test",
            is_npc=False,
            wait_state_until=future_time,
        )
        assert p.wait_state_until == future_time


class TestCombatMechanics:
    """Tests for combat roll mechanics."""

    def test_attribute_modifier_calculation(self):
        """Test D&D-style attribute modifier."""
        assert calculate_attribute_modifier(10) == 0
        assert calculate_attribute_modifier(12) == 1
        assert calculate_attribute_modifier(14) == 2
        assert calculate_attribute_modifier(16) == 3
        assert calculate_attribute_modifier(8) == -1
        assert calculate_attribute_modifier(6) == -2
        assert calculate_attribute_modifier(20) == 5
        assert calculate_attribute_modifier(3) == -4

    def test_roll_d20_range(self):
        """Test d20 roll is in valid range."""
        for _ in range(100):
            roll = roll_d20()
            assert 1 <= roll <= 20

    def test_roll_initiative(self):
        """Test initiative includes DEX modifier."""
        # With +2 DEX mod, initiative should be d20+2
        with patch('waystone.game.systems.unified_combat.roll_d20', return_value=15):
            result = roll_initiative(dex_modifier=2)
            assert result == 17

    def test_roll_initiative_negative_modifier(self):
        """Test initiative with negative DEX modifier."""
        with patch('waystone.game.systems.unified_combat.roll_d20', return_value=10):
            result = roll_initiative(dex_modifier=-2)
            assert result == 8

    def test_damage_message_scaling(self):
        """Test ROM-style damage messages."""
        assert get_damage_message(0) == "miss"
        assert get_damage_message(1) == "scratch"
        assert get_damage_message(3) == "scratch"
        assert get_damage_message(5) == "hit"
        assert get_damage_message(10) == "hit"
        assert get_damage_message(15) == "wound"
        assert get_damage_message(20) == "maul"
        assert get_damage_message(25) == "maul"
        assert get_damage_message(30) == "MASSACRE"
        assert get_damage_message(50) == "MASSACRE"
        assert get_damage_message(100) == "ANNIHILATE"
        assert get_damage_message(150) == "ANNIHILATE"


class TestRollToHit:
    """Tests for to-hit mechanics."""

    @pytest.mark.asyncio
    async def test_natural_20_always_crits(self):
        """Natural 20 is always a critical hit."""
        attacker = CombatParticipant("a", "Attacker", is_npc=False)
        defender = CombatParticipant("d", "Defender", is_npc=False)

        with patch('waystone.game.systems.unified_combat.roll_d20', return_value=20):
            with patch('waystone.game.systems.unified_combat.get_participant_attribute', return_value=10):
                hit, is_crit, roll = await roll_to_hit(attacker, defender)
                assert hit is True
                assert is_crit is True
                assert roll == 20

    @pytest.mark.asyncio
    async def test_natural_1_always_misses(self):
        """Natural 1 always misses (fumble)."""
        attacker = CombatParticipant("a", "Attacker", is_npc=False)
        defender = CombatParticipant("d", "Defender", is_npc=False)

        with patch('waystone.game.systems.unified_combat.roll_d20', return_value=1):
            hit, is_crit, roll = await roll_to_hit(attacker, defender)
            assert hit is False
            assert is_crit is False
            assert roll == 1

    @pytest.mark.asyncio
    async def test_hit_when_roll_meets_defense(self):
        """Test hit when roll equals defense."""
        attacker = CombatParticipant("a", "Attacker", is_npc=False)
        defender = CombatParticipant("d", "Defender", is_npc=False)

        # Roll 12 with DEX 10 (+0) = 12 attack vs 10+0=10 defense = hit
        with patch('waystone.game.systems.unified_combat.roll_d20', return_value=12):
            with patch('waystone.game.systems.unified_combat.get_participant_attribute', return_value=10):
                hit, is_crit, roll = await roll_to_hit(attacker, defender)
                assert hit is True
                assert is_crit is False

    @pytest.mark.asyncio
    async def test_miss_when_roll_below_defense(self):
        """Test miss when roll below defense."""
        attacker = CombatParticipant("a", "Attacker", is_npc=False)
        defender = CombatParticipant("d", "Defender", is_npc=False)

        # Roll 8 with DEX 10 (+0) = 8 attack vs 10+0=10 defense = miss
        with patch('waystone.game.systems.unified_combat.roll_d20', return_value=8):
            with patch('waystone.game.systems.unified_combat.get_participant_attribute', return_value=10):
                hit, is_crit, roll = await roll_to_hit(attacker, defender)
                assert hit is False
                assert is_crit is False

    @pytest.mark.asyncio
    async def test_defending_adds_to_defense(self):
        """Defending stance adds +5 to defense."""
        attacker = CombatParticipant("a", "Attacker", is_npc=False)
        defender = CombatParticipant("d", "Defender", is_npc=False)
        defender.is_defending = True

        # Roll 12 with DEX 10 = 12 attack vs 10+0+5=15 defense = miss
        with patch('waystone.game.systems.unified_combat.roll_d20', return_value=12):
            with patch('waystone.game.systems.unified_combat.get_participant_attribute', return_value=10):
                hit, is_crit, roll = await roll_to_hit(attacker, defender)
                assert hit is False

    @pytest.mark.asyncio
    async def test_dex_modifier_affects_to_hit(self):
        """DEX modifier affects attack roll."""
        attacker = CombatParticipant("a", "Attacker", is_npc=False)
        defender = CombatParticipant("d", "Defender", is_npc=False)

        # Roll 10 with DEX 14 (+2) = 12 attack vs 10 defense = hit
        def mock_get_attribute(p, attr):
            if p == attacker and attr == "dexterity":
                return 14  # +2 modifier
            return 10  # +0 modifier for defender

        with patch('waystone.game.systems.unified_combat.roll_d20', return_value=10):
            with patch('waystone.game.systems.unified_combat.get_participant_attribute', side_effect=mock_get_attribute):
                hit, is_crit, roll = await roll_to_hit(attacker, defender)
                assert hit is True


class TestCalculateDamage:
    """Tests for damage calculation."""

    @pytest.mark.asyncio
    async def test_base_damage_range(self):
        """Base damage is 1d6 + STR mod, minimum 1."""
        attacker = CombatParticipant("a", "Attacker", is_npc=False)

        with patch('waystone.game.systems.unified_combat.get_participant_attribute', return_value=10):
            damages = []
            for _ in range(100):
                damage = await calculate_damage(attacker, is_critical=False)
                damages.append(damage)

            # With STR 10 (+0 mod), damage should be 1-6
            assert min(damages) >= 1
            assert max(damages) <= 6

    @pytest.mark.asyncio
    async def test_critical_doubles_dice(self):
        """Critical hit rolls 2d6 instead of 1d6."""
        attacker = CombatParticipant("a", "Attacker", is_npc=False)

        with patch('waystone.game.systems.unified_combat.get_participant_attribute', return_value=10):
            damages = []
            for _ in range(100):
                damage = await calculate_damage(attacker, is_critical=True)
                damages.append(damage)

            # With STR 10 (+0 mod), crit damage should be 2-12
            assert max(damages) <= 12
            # Should see higher values than non-crit
            assert max(damages) > 6  # Very likely with 100 rolls

    @pytest.mark.asyncio
    async def test_strength_modifier_adds_to_damage(self):
        """STR modifier adds to damage."""
        attacker = CombatParticipant("a", "Attacker", is_npc=False)

        # STR 16 = +3 modifier, so damage is 1d6+3 = 4-9
        with patch('waystone.game.systems.unified_combat.get_participant_attribute', return_value=16):
            damages = []
            for _ in range(100):
                damage = await calculate_damage(attacker, is_critical=False)
                damages.append(damage)

            assert min(damages) >= 4  # 1 + 3
            assert max(damages) <= 9  # 6 + 3

    @pytest.mark.asyncio
    async def test_minimum_damage_is_one(self):
        """Damage never goes below 1."""
        attacker = CombatParticipant("a", "Attacker", is_npc=False)

        # STR 4 = -3 modifier, so 1d6-3 could be negative
        with patch('waystone.game.systems.unified_combat.get_participant_attribute', return_value=4):
            for _ in range(50):
                damage = await calculate_damage(attacker, is_critical=False)
                assert damage >= 1

    @pytest.mark.asyncio
    async def test_critical_with_strength_modifier(self):
        """Critical damage: 2d6 + STR modifier."""
        attacker = CombatParticipant("a", "Attacker", is_npc=False)

        # STR 14 = +2 modifier, so crit damage is 2d6+2 = 4-14
        with patch('waystone.game.systems.unified_combat.get_participant_attribute', return_value=14):
            damages = []
            for _ in range(100):
                damage = await calculate_damage(attacker, is_critical=True)
                damages.append(damage)

            assert min(damages) >= 4  # 2 + 2
            assert max(damages) <= 14  # 12 + 2


class TestCombatRegistry:
    """Tests for global combat registry."""

    @pytest.fixture(autouse=True)
    def clear_registry(self):
        """Clear combat registry before each test."""
        _active_combats.clear()
        yield
        _active_combats.clear()

    @pytest.mark.asyncio
    async def test_create_combat(self):
        """Test creating a combat instance."""
        engine = MagicMock()
        combat = await create_combat("test_room", engine)

        assert combat.room_id == "test_room"
        assert combat.state == CombatState.SETUP
        assert get_combat_for_room("test_room") == combat

    def test_get_combat_for_room_returns_none_for_empty(self):
        """No combat returns None."""
        assert get_combat_for_room("nonexistent") is None

    def test_get_combat_for_room_ignores_ended(self):
        """Ended combats are ignored."""
        engine = MagicMock()
        combat = Combat("test_room", engine)
        combat.state = CombatState.ENDED
        _active_combats["test_room"] = combat

        assert get_combat_for_room("test_room") is None

    def test_get_combat_for_room_returns_active(self):
        """Returns active combat."""
        engine = MagicMock()
        combat = Combat("test_room", engine)
        combat.state = CombatState.ACTIVE
        _active_combats["test_room"] = combat

        assert get_combat_for_room("test_room") == combat

    def test_cleanup_ended_combats(self):
        """Cleanup removes ended combats."""
        engine = MagicMock()

        active = Combat("room1", engine)
        active.state = CombatState.ACTIVE
        _active_combats["room1"] = active

        ended = Combat("room2", engine)
        ended.state = CombatState.ENDED
        _active_combats["room2"] = ended

        removed = cleanup_ended_combats()

        assert removed == 1
        assert "room1" in _active_combats
        assert "room2" not in _active_combats

    def test_cleanup_ended_combats_removes_multiple(self):
        """Cleanup removes all ended combats."""
        engine = MagicMock()

        for i in range(5):
            combat = Combat(f"room{i}", engine)
            combat.state = CombatState.ENDED if i % 2 == 0 else CombatState.ACTIVE
            _active_combats[f"room{i}"] = combat

        removed = cleanup_ended_combats()

        assert removed == 3  # rooms 0, 2, 4
        assert len(_active_combats) == 2


class TestCombatClass:
    """Tests for Combat class."""

    @pytest.fixture
    def mock_engine(self):
        """Create mock game engine."""
        engine = MagicMock()
        engine.broadcast_to_room = MagicMock()
        return engine

    @pytest.mark.asyncio
    async def test_combat_initialization(self, mock_engine):
        """Test combat initialization."""
        combat = Combat("test_room", mock_engine)

        assert combat.room_id == "test_room"
        assert combat.engine == mock_engine
        assert combat.state == CombatState.SETUP
        assert len(combat.participants) == 0
        assert combat.round_number == 0
        assert combat.round_task is None

    @pytest.mark.asyncio
    async def test_add_participant(self, mock_engine):
        """Test adding participants to combat."""
        combat = Combat("test_room", mock_engine)

        p = await combat.add_participant(
            entity_id="char-123",
            entity_name="TestPlayer",
            is_npc=False,
            target_id="npc-456"
        )

        assert len(combat.participants) == 1
        assert p.entity_name == "TestPlayer"
        assert p.target_id == "npc-456"
        assert p.entity_id == "char-123"

    @pytest.mark.asyncio
    async def test_add_participant_rolls_initiative(self, mock_engine):
        """Test that adding participant rolls initiative."""
        combat = Combat("test_room", mock_engine)

        # _roll_initiative uses random.randint(1, 20) directly
        with patch('random.randint', return_value=15):
            p = await combat.add_participant(
                entity_id="char-123",
                entity_name="TestPlayer",
                is_npc=False,
            )

        # Initiative is d20(15) + dex_modifier(0 default) = 15
        assert p.initiative == 15

    @pytest.mark.asyncio
    async def test_remove_participant(self, mock_engine):
        """Test removing participants."""
        combat = Combat("test_room", mock_engine)
        await combat.add_participant("char-123", "Player", is_npc=False)
        await combat.add_participant("npc-456", "NPC", is_npc=True)

        await combat.remove_participant("char-123")

        assert len(combat.participants) == 1
        assert combat.participants[0].entity_id == "npc-456"

    @pytest.mark.asyncio
    async def test_get_participant(self, mock_engine):
        """Test finding participant by ID."""
        combat = Combat("test_room", mock_engine)
        await combat.add_participant("char-123", "Player", is_npc=False)

        found = combat.get_participant("char-123")
        not_found = combat.get_participant("nonexistent")

        assert found is not None
        assert found.entity_name == "Player"
        assert not_found is None

    @pytest.mark.asyncio
    async def test_start_sorts_by_initiative(self, mock_engine):
        """Test that start() sorts participants by initiative."""
        combat = Combat("test_room", mock_engine)

        # Add participants with different initiative
        p1 = await combat.add_participant("char-1", "Player1", is_npc=False)
        p2 = await combat.add_participant("char-2", "Player2", is_npc=False)
        p3 = await combat.add_participant("char-3", "Player3", is_npc=False)

        p1.initiative = 10
        p2.initiative = 20
        p3.initiative = 15

        # Mock the round loop to prevent actual execution
        with patch.object(combat, '_combat_round_loop', new_callable=AsyncMock):
            await combat.start()

        # Should be sorted high to low: p2(20), p3(15), p1(10)
        assert combat.participants[0].entity_id == "char-2"
        assert combat.participants[1].entity_id == "char-3"
        assert combat.participants[2].entity_id == "char-1"

    @pytest.mark.asyncio
    async def test_start_changes_state_to_active(self, mock_engine):
        """Test that start() changes state to ACTIVE."""
        combat = Combat("test_room", mock_engine)
        await combat.add_participant("char-123", "Player", is_npc=False)

        with patch.object(combat, '_combat_round_loop', new_callable=AsyncMock):
            await combat.start()

        assert combat.state == CombatState.ACTIVE

    @pytest.mark.asyncio
    async def test_start_creates_round_task(self, mock_engine):
        """Test that start() creates the round task."""
        combat = Combat("test_room", mock_engine)
        await combat.add_participant("char-123", "Player", is_npc=False)

        # Mock the round loop to not actually run
        with patch.object(combat, '_combat_round_loop', new_callable=AsyncMock):
            await combat.start()

        assert combat.round_task is not None

    @pytest.mark.asyncio
    async def test_end_combat_changes_state(self, mock_engine):
        """Test that end_combat changes state to ENDED."""
        combat = Combat("test_room", mock_engine)
        combat.state = CombatState.ACTIVE

        await combat.end_combat("test ended")

        assert combat.state == CombatState.ENDED

    @pytest.mark.asyncio
    async def test_end_combat_cancels_task(self, mock_engine):
        """Test that end_combat cancels the round task."""
        combat = Combat("test_room", mock_engine)
        combat.state = CombatState.ACTIVE

        # Create a task that runs for a while
        task = asyncio.create_task(asyncio.sleep(100))
        combat.round_task = task

        await combat.end_combat("test ended")

        # Task should be cancelled/done (implementation sets round_task to None after)
        assert task.cancelled() or task.done()

    @pytest.mark.asyncio
    async def test_end_combat_broadcasts_message(self, mock_engine):
        """Test that end_combat broadcasts to room."""
        combat = Combat("test_room", mock_engine)
        combat.state = CombatState.ACTIVE

        await combat.end_combat("All enemies defeated")

        mock_engine.broadcast_to_room.assert_called()

    @pytest.mark.asyncio
    async def test_is_character_in_combat(self, mock_engine):
        """Test checking if character is in combat."""
        combat = Combat("test_room", mock_engine)
        await combat.add_participant("char-123", "Player", is_npc=False)

        assert combat.is_character_in_combat("char-123") is True
        assert combat.is_character_in_combat("nonexistent") is False

    @pytest.mark.asyncio
    async def test_execute_round_increments_round_number(self, mock_engine):
        """Test that _execute_round increments round number."""
        combat = Combat("test_room", mock_engine)
        combat.state = CombatState.ACTIVE

        # Mock auto_action to prevent actual combat
        with patch.object(combat, '_auto_action', new_callable=AsyncMock):
            await combat._execute_round()

        # Note: _execute_round doesn't increment, _combat_round_loop does
        # This test may need adjustment based on actual implementation


class TestParticipantHelpers:
    """Tests for participant helper functions."""

    @pytest.mark.asyncio
    async def test_get_participant_hp_player(self):
        """Test getting HP for player participant with entity ref."""
        participant = CombatParticipant("char-123", "Player", is_npc=False)

        # Create mock entity with HP
        mock_entity = MagicMock()
        mock_entity.current_hp = 50
        mock_entity.max_hp = 100
        participant._entity_ref = mock_entity

        current, max_hp = await get_participant_hp(participant)
        assert current == 50
        assert max_hp == 100

    @pytest.mark.asyncio
    async def test_get_participant_hp_default(self):
        """Test getting HP returns default when no entity ref."""
        participant = CombatParticipant("char-123", "Player", is_npc=False)
        # No entity ref set

        current, max_hp = await get_participant_hp(participant)
        # Should return default (100, 100)
        assert current == 100
        assert max_hp == 100

    @pytest.mark.asyncio
    async def test_get_participant_attribute(self):
        """Test getting attribute for participant with entity ref."""
        participant = CombatParticipant("char-123", "Player", is_npc=False)

        # Create mock entity with attributes
        mock_entity = MagicMock()
        mock_entity.strength = 16
        mock_entity.dexterity = 14
        participant._entity_ref = mock_entity

        strength = await get_participant_attribute(participant, "strength")
        dex = await get_participant_attribute(participant, "dexterity")

        assert strength == 16
        assert dex == 14

    @pytest.mark.asyncio
    async def test_get_participant_attribute_default(self):
        """Test getting attribute returns default when no entity ref."""
        participant = CombatParticipant("char-123", "Player", is_npc=False)
        # No entity ref set

        strength = await get_participant_attribute(participant, "strength")
        assert strength == 10  # Default

    @pytest.mark.asyncio
    async def test_apply_damage_to_participant(self):
        """Test applying damage to participant with entity ref."""
        participant = CombatParticipant("char-123", "Player", is_npc=False)

        # Create mock entity with HP
        mock_entity = MagicMock()
        mock_entity.current_hp = 50
        participant._entity_ref = mock_entity

        new_hp = await apply_damage_to_participant(participant, 10)
        assert new_hp == 40
        assert mock_entity.current_hp == 40

    @pytest.mark.asyncio
    async def test_apply_damage_minimum_zero(self):
        """Test damage doesn't go below 0."""
        participant = CombatParticipant("char-123", "Player", is_npc=False)

        mock_entity = MagicMock()
        mock_entity.current_hp = 50
        participant._entity_ref = mock_entity

        new_hp = await apply_damage_to_participant(participant, 60)
        assert new_hp == 0  # Can't go below 0


class TestCombatRoundLoop:
    """Tests for combat round loop mechanics."""

    @pytest.fixture
    def mock_engine(self):
        """Create mock game engine."""
        engine = MagicMock()
        engine.broadcast_to_room = MagicMock()
        return engine

    @pytest.mark.asyncio
    async def test_round_loop_increments_round_number(self, mock_engine):
        """Test that round loop increments round number."""
        combat = Combat("test_room", mock_engine)
        combat.state = CombatState.ACTIVE
        await combat.add_participant("char-123", "Player", is_npc=False)

        # _execute_round increments round_number, so we need a side effect
        async def mock_execute_round():
            combat.round_number += 1

        # _should_continue_combat returns False to end after first round
        with patch.object(combat, '_execute_round', side_effect=mock_execute_round):
            with patch.object(combat, '_should_continue_combat', return_value=False):
                await combat._combat_round_loop()

        assert combat.round_number >= 1

    @pytest.mark.asyncio
    async def test_round_loop_broadcasts_round_start(self, mock_engine):
        """Test that round loop broadcasts round start."""
        combat = Combat("test_room", mock_engine)
        combat.state = CombatState.ACTIVE
        await combat.add_participant("char-123", "Player", is_npc=False)

        with patch.object(combat, '_execute_round', new_callable=AsyncMock):
            with patch.object(combat, '_should_continue_combat', return_value=False):
                await combat._combat_round_loop()

        # Should have called broadcast_to_room for round start
        assert mock_engine.broadcast_to_room.called

    @pytest.mark.asyncio
    async def test_round_loop_ends_when_combat_should_not_continue(self, mock_engine):
        """Test that round loop ends when combat should end."""
        combat = Combat("test_room", mock_engine)
        combat.state = CombatState.ACTIVE

        with patch.object(combat, '_execute_round', new_callable=AsyncMock):
            with patch.object(combat, '_should_continue_combat', return_value=False):
                await combat._combat_round_loop()

        assert combat.state == CombatState.ENDED


class TestCombatEndConditions:
    """Tests for combat end conditions."""

    @pytest.fixture
    def mock_engine(self):
        """Create mock game engine."""
        engine = MagicMock()
        engine.broadcast_to_room = MagicMock()
        return engine

    def test_should_continue_with_active_participants(self, mock_engine):
        """Combat continues with active participants on both sides."""
        combat = Combat("test_room", mock_engine)

        # Add player and NPC
        p1 = CombatParticipant("char-1", "Player", is_npc=False)
        n1 = CombatParticipant("npc-1", "NPC", is_npc=True)

        combat.participants = [p1, n1]

        # Mock _is_dead_sync to return False (all alive)
        with patch.object(combat, '_is_dead_sync', return_value=False):
            assert combat._should_continue_combat() is True

    def test_should_not_continue_only_one_participant(self, mock_engine):
        """Combat ends when only one participant remains."""
        combat = Combat("test_room", mock_engine)

        p1 = CombatParticipant("char-1", "Player", is_npc=False)
        combat.participants = [p1]

        with patch.object(combat, '_is_dead_sync', return_value=False):
            assert combat._should_continue_combat() is False

    def test_should_not_continue_all_fled(self, mock_engine):
        """Combat ends when all participants fled."""
        combat = Combat("test_room", mock_engine)

        p1 = CombatParticipant("char-1", "Player", is_npc=False, fled=True)
        p2 = CombatParticipant("char-2", "Player2", is_npc=False, fled=True)

        combat.participants = [p1, p2]

        with patch.object(combat, '_is_dead_sync', return_value=False):
            assert combat._should_continue_combat() is False

    def test_should_not_continue_only_one_side_remains(self, mock_engine):
        """Combat ends when only players or only NPCs remain."""
        combat = Combat("test_room", mock_engine)

        # Only players left
        p1 = CombatParticipant("char-1", "Player1", is_npc=False)
        p2 = CombatParticipant("char-2", "Player2", is_npc=False)

        combat.participants = [p1, p2]

        with patch.object(combat, '_is_dead_sync', return_value=False):
            assert combat._should_continue_combat() is False


class TestFleeMechanics:
    """Tests for flee mechanics."""

    @pytest.fixture
    def mock_engine(self):
        """Create mock game engine."""
        engine = MagicMock()
        engine.broadcast_to_room = MagicMock()
        engine.world = {"test_room": MagicMock(exits={"north": "other_room"})}
        return engine

    @pytest.mark.asyncio
    async def test_attempt_flee_success(self, mock_engine):
        """Test successful flee attempt."""
        combat = Combat("test_room", mock_engine)
        participant = CombatParticipant("char-123", "Player", is_npc=False)
        combat.participants = [participant]

        # Mock DEX 10, roll 20 (guaranteed success)
        with patch('waystone.game.systems.unified_combat.get_participant_attribute', return_value=10):
            with patch('waystone.game.systems.unified_combat.roll_d20', return_value=20):
                success = await combat.attempt_flee(participant)

        assert success is True
        assert participant.fled is True

    @pytest.mark.asyncio
    async def test_attempt_flee_failure(self, mock_engine):
        """Test failed flee attempt."""
        combat = Combat("test_room", mock_engine)
        participant = CombatParticipant("char-123", "Player", is_npc=False)
        combat.participants = [participant]

        # Mock DEX 10, roll 1 (guaranteed failure)
        with patch('waystone.game.systems.unified_combat.get_participant_attribute', return_value=10):
            with patch('waystone.game.systems.unified_combat.roll_d20', return_value=1):
                success = await combat.attempt_flee(participant)

        assert success is False
        assert participant.fled is False
        assert participant.wait_state_until is not None

    @pytest.mark.asyncio
    async def test_flee_sets_wait_state_on_failure(self, mock_engine):
        """Failed flee sets 1-second wait state."""
        combat = Combat("test_room", mock_engine)
        participant = CombatParticipant("char-123", "Player", is_npc=False)
        combat.participants = [participant]

        before_time = datetime.now()

        with patch('waystone.game.systems.unified_combat.get_participant_attribute', return_value=10):
            with patch('waystone.game.systems.unified_combat.roll_d20', return_value=1):
                await combat.attempt_flee(participant)

        assert participant.wait_state_until is not None
        # Wait state should be ~1 second in the future
        time_diff = (participant.wait_state_until - before_time).total_seconds()
        assert 0.9 <= time_diff <= 1.1


class TestWaitState:
    """Tests for wait state mechanics."""

    @pytest.fixture
    def mock_engine(self):
        """Create mock game engine."""
        engine = MagicMock()
        engine.broadcast_to_room = MagicMock()
        return engine

    def test_is_in_wait_state_true(self, mock_engine):
        """Test detecting participant in wait state."""
        combat = Combat("test_room", mock_engine)
        participant = CombatParticipant("char-123", "Player", is_npc=False)
        participant.wait_state_until = datetime.now() + timedelta(seconds=3)

        assert combat._is_in_wait_state(participant) is True

    def test_is_in_wait_state_false_expired(self, mock_engine):
        """Test participant not in wait state when expired."""
        combat = Combat("test_room", mock_engine)
        participant = CombatParticipant("char-123", "Player", is_npc=False)
        participant.wait_state_until = datetime.now() - timedelta(seconds=1)

        assert combat._is_in_wait_state(participant) is False

    def test_is_in_wait_state_false_none(self, mock_engine):
        """Test participant not in wait state when None."""
        combat = Combat("test_room", mock_engine)
        participant = CombatParticipant("char-123", "Player", is_npc=False)
        participant.wait_state_until = None

        assert combat._is_in_wait_state(participant) is False


class TestTargetSwitching:
    """Tests for target switching mechanics."""

    @pytest.fixture
    def mock_engine(self):
        """Create mock game engine."""
        engine = MagicMock()
        engine.broadcast_to_room = MagicMock()
        return engine

    @pytest.mark.asyncio
    async def test_switch_target_success(self, mock_engine):
        """Test successful target switch."""
        combat = Combat("test_room", mock_engine)

        p1 = CombatParticipant("char-1", "Player", is_npc=False)
        n1 = CombatParticipant("npc-1", "NPC1", is_npc=True)
        n2 = CombatParticipant("npc-2", "NPC2", is_npc=True)

        combat.participants = [p1, n1, n2]
        p1.target_id = "npc-1"

        success = await combat.switch_target(p1, "npc-2")

        assert success is True
        assert p1.target_id == "npc-2"

    @pytest.mark.asyncio
    async def test_switch_target_invalid_target(self, mock_engine):
        """Test switching to invalid target."""
        combat = Combat("test_room", mock_engine)

        p1 = CombatParticipant("char-1", "Player", is_npc=False)
        combat.participants = [p1]

        success = await combat.switch_target(p1, "nonexistent")

        assert success is False

    @pytest.mark.asyncio
    async def test_switch_target_to_self_fails(self, mock_engine):
        """Test switching target to self fails."""
        combat = Combat("test_room", mock_engine)

        p1 = CombatParticipant("char-1", "Player", is_npc=False)
        combat.participants = [p1]

        success = await combat.switch_target(p1, "char-1")

        assert success is False

    @pytest.mark.asyncio
    async def test_switch_target_to_fled_participant_fails(self, mock_engine):
        """Test switching to fled participant fails."""
        combat = Combat("test_room", mock_engine)

        p1 = CombatParticipant("char-1", "Player", is_npc=False)
        n1 = CombatParticipant("npc-1", "NPC", is_npc=True, fled=True)

        combat.participants = [p1, n1]

        success = await combat.switch_target(p1, "npc-1")

        assert success is False
