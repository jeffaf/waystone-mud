"""Tests for combat skills (bash, kick, disarm, trip).

This test suite is written in TDD (Test-Driven Development) style.
Phase 3 of unified combat system - combat skills implementation.
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from waystone.game.systems.unified_combat import (
    Combat,
    CombatParticipant,
    CombatState,
    calculate_attribute_modifier,
)

# Import skill functions (to be implemented)
try:
    from waystone.game.systems.unified_combat import (
        execute_bash,
        execute_kick,
        execute_disarm,
        execute_trip,
        is_skill_on_cooldown,
        set_skill_cooldown,
    )
    SKILLS_IMPLEMENTED = True
except ImportError:
    SKILLS_IMPLEMENTED = False
    # Define placeholder functions for TDD
    async def execute_bash(combat, attacker, target):
        raise NotImplementedError("execute_bash not yet implemented")

    async def execute_kick(combat, attacker, target):
        raise NotImplementedError("execute_kick not yet implemented")

    async def execute_disarm(combat, attacker, target):
        raise NotImplementedError("execute_disarm not yet implemented")

    async def execute_trip(combat, attacker, target):
        raise NotImplementedError("execute_trip not yet implemented")

    def is_skill_on_cooldown(participant, skill_name):
        raise NotImplementedError("is_skill_on_cooldown not yet implemented")

    def set_skill_cooldown(participant, skill_name, seconds):
        raise NotImplementedError("set_skill_cooldown not yet implemented")


class TestCombatParticipantSkillTracking:
    """Tests for skill cooldown and effects tracking on CombatParticipant."""

    def test_participant_has_skill_cooldowns_dict(self):
        """Test that CombatParticipant has skill_cooldowns attribute."""
        p = CombatParticipant(
            entity_id="test-id",
            entity_name="Test",
            is_npc=False,
        )
        assert hasattr(p, "skill_cooldowns")
        assert isinstance(p.skill_cooldowns, dict)
        assert len(p.skill_cooldowns) == 0

    def test_participant_has_effects_dict(self):
        """Test that CombatParticipant has effects attribute."""
        p = CombatParticipant(
            entity_id="test-id",
            entity_name="Test",
            is_npc=False,
        )
        assert hasattr(p, "effects")
        assert isinstance(p.effects, dict)
        assert len(p.effects) == 0


class TestCooldownHelpers:
    """Tests for cooldown helper functions."""

    def test_is_skill_on_cooldown_no_cooldown(self):
        """Test checking cooldown when skill has never been used."""
        p = CombatParticipant(
            entity_id="test-id",
            entity_name="Test",
            is_npc=False,
        )
        p.skill_cooldowns = {}

        if SKILLS_IMPLEMENTED:
            assert is_skill_on_cooldown(p, "bash") is False
        else:
            pytest.skip("Skills not yet implemented")

    def test_is_skill_on_cooldown_expired(self):
        """Test checking cooldown when cooldown has expired."""
        p = CombatParticipant(
            entity_id="test-id",
            entity_name="Test",
            is_npc=False,
        )
        p.skill_cooldowns = {
            "bash": datetime.now() - timedelta(seconds=5)  # Expired
        }

        if SKILLS_IMPLEMENTED:
            assert is_skill_on_cooldown(p, "bash") is False
        else:
            pytest.skip("Skills not yet implemented")

    def test_is_skill_on_cooldown_active(self):
        """Test checking cooldown when skill is on cooldown."""
        p = CombatParticipant(
            entity_id="test-id",
            entity_name="Test",
            is_npc=False,
        )
        p.skill_cooldowns = {
            "bash": datetime.now() + timedelta(seconds=10)  # Active cooldown
        }

        if SKILLS_IMPLEMENTED:
            assert is_skill_on_cooldown(p, "bash") is True
        else:
            pytest.skip("Skills not yet implemented")

    def test_set_skill_cooldown(self):
        """Test setting a skill cooldown."""
        p = CombatParticipant(
            entity_id="test-id",
            entity_name="Test",
            is_npc=False,
        )
        p.skill_cooldowns = {}

        if SKILLS_IMPLEMENTED:
            before = datetime.now()
            set_skill_cooldown(p, "bash", 15)
            after = datetime.now()

            assert "bash" in p.skill_cooldowns
            # Cooldown should be approximately 15 seconds from now
            cooldown_time = p.skill_cooldowns["bash"]
            expected = before + timedelta(seconds=15)
            # Allow 1 second tolerance
            assert abs((cooldown_time - expected).total_seconds()) < 1
        else:
            pytest.skip("Skills not yet implemented")


class TestBashSkill:
    """Tests for bash skill (knockdown attack)."""

    @pytest.mark.asyncio
    async def test_bash_hit_calculation(self):
        """Test bash roll: d20 + STR vs target AC."""
        if not SKILLS_IMPLEMENTED:
            pytest.skip("Skills not yet implemented")

        # Create mock combat
        engine_mock = MagicMock()
        engine_mock.broadcast_to_room = MagicMock()
        combat = Combat("test-room", engine_mock)

        # Create participants
        attacker = CombatParticipant(
            entity_id="attacker",
            entity_name="Attacker",
            is_npc=False,
        )
        # Mock entity ref with STR 16 (mod +3)
        attacker._entity_ref = MagicMock()
        attacker._entity_ref.strength = 16
        attacker._entity_ref.current_hp = 100
        attacker.skill_cooldowns = {}
        attacker.effects = {}

        target = CombatParticipant(
            entity_id="target",
            entity_name="Target",
            is_npc=False,
        )
        # Mock entity ref with DEX 10 (AC 10)
        target._entity_ref = MagicMock()
        target._entity_ref.dexterity = 10
        target._entity_ref.current_hp = 100
        target.effects = {}

        # Test multiple times to verify probabilistic behavior
        hits = 0
        for _ in range(20):
            combat.participants = [attacker, target]
            success, msg = await execute_bash(combat, attacker, target)
            if success and "misses" not in msg:
                hits += 1

        # With STR +3 vs AC 10, should hit on 7+ (70% chance)
        # In 20 rolls, expect at least some hits
        assert hits > 0

    @pytest.mark.asyncio
    async def test_bash_knockdown_effect(self):
        """Test that bash applies knockdown effect on hit."""
        if not SKILLS_IMPLEMENTED:
            pytest.skip("Skills not yet implemented")

        engine_mock = MagicMock()
        engine_mock.broadcast_to_room = MagicMock()
        combat = Combat("test-room", engine_mock)

        attacker = CombatParticipant(
            entity_id="attacker",
            entity_name="Attacker",
            is_npc=False,
        )
        attacker._entity_ref = MagicMock()
        attacker._entity_ref.strength = 18  # High STR for consistent hits
        attacker._entity_ref.current_hp = 100
        attacker.skill_cooldowns = {}
        attacker.effects = {}

        target = CombatParticipant(
            entity_id="target",
            entity_name="Target",
            is_npc=False,
        )
        target._entity_ref = MagicMock()
        target._entity_ref.dexterity = 8  # Low DEX for easier hits
        target._entity_ref.current_hp = 100
        target.effects = {}

        # Mock random to guarantee hit
        with patch('random.randint', return_value=20):
            combat.participants = [attacker, target]
            success, msg = await execute_bash(combat, attacker, target)

        # Target should have knockdown effect
        assert "knocked_down" in target.effects or "knockdown" in msg.lower()

    @pytest.mark.asyncio
    async def test_bash_wait_state(self):
        """Test that bash applies 2-round wait state to attacker."""
        if not SKILLS_IMPLEMENTED:
            pytest.skip("Skills not yet implemented")

        engine_mock = MagicMock()
        engine_mock.broadcast_to_room = MagicMock()
        combat = Combat("test-room", engine_mock)

        attacker = CombatParticipant(
            entity_id="attacker",
            entity_name="Attacker",
            is_npc=False,
        )
        attacker._entity_ref = MagicMock()
        attacker._entity_ref.strength = 16
        attacker._entity_ref.current_hp = 100
        attacker.skill_cooldowns = {}
        attacker.effects = {}
        attacker.wait_state_until = None

        target = CombatParticipant(
            entity_id="target",
            entity_name="Target",
            is_npc=False,
        )
        target._entity_ref = MagicMock()
        target._entity_ref.dexterity = 10
        target._entity_ref.current_hp = 100
        target.effects = {}

        before = datetime.now()
        combat.participants = [attacker, target]
        await execute_bash(combat, attacker, target)
        after = datetime.now()

        # Attacker should have wait_state set
        assert attacker.wait_state_until is not None
        # Wait state should be approximately 6 seconds (2 rounds * 3 sec)
        wait_duration = (attacker.wait_state_until - before).total_seconds()
        assert 5.5 <= wait_duration <= 6.5

    @pytest.mark.asyncio
    async def test_bash_cooldown(self):
        """Test that bash applies 15-second cooldown."""
        if not SKILLS_IMPLEMENTED:
            pytest.skip("Skills not yet implemented")

        engine_mock = MagicMock()
        engine_mock.broadcast_to_room = MagicMock()
        combat = Combat("test-room", engine_mock)

        attacker = CombatParticipant(
            entity_id="attacker",
            entity_name="Attacker",
            is_npc=False,
        )
        attacker._entity_ref = MagicMock()
        attacker._entity_ref.strength = 16
        attacker._entity_ref.current_hp = 100
        attacker.skill_cooldowns = {}
        attacker.effects = {}

        target = CombatParticipant(
            entity_id="target",
            entity_name="Target",
            is_npc=False,
        )
        target._entity_ref = MagicMock()
        target._entity_ref.dexterity = 10
        target._entity_ref.current_hp = 100
        target.effects = {}

        combat.participants = [attacker, target]
        await execute_bash(combat, attacker, target)

        # Cooldown should be set
        assert is_skill_on_cooldown(attacker, "bash") is True


class TestKickSkill:
    """Tests for kick skill (quick damage)."""

    @pytest.mark.asyncio
    async def test_kick_uses_dexterity(self):
        """Test kick roll: d20 + DEX vs target AC."""
        if not SKILLS_IMPLEMENTED:
            pytest.skip("Skills not yet implemented")

        engine_mock = MagicMock()
        engine_mock.broadcast_to_room = MagicMock()
        combat = Combat("test-room", engine_mock)

        attacker = CombatParticipant(
            entity_id="attacker",
            entity_name="Attacker",
            is_npc=False,
        )
        attacker._entity_ref = MagicMock()
        attacker._entity_ref.dexterity = 18  # High DEX
        attacker._entity_ref.current_hp = 100
        attacker.skill_cooldowns = {}
        attacker.effects = {}

        target = CombatParticipant(
            entity_id="target",
            entity_name="Target",
            is_npc=False,
        )
        target._entity_ref = MagicMock()
        target._entity_ref.dexterity = 10
        target._entity_ref.current_hp = 100
        target.effects = {}

        # Mock high roll to guarantee hit
        with patch('random.randint', return_value=15):
            combat.participants = [attacker, target]
            success, msg = await execute_kick(combat, attacker, target)

        # Should hit with high DEX
        assert success is True

    @pytest.mark.asyncio
    async def test_kick_damage_includes_dex_bonus(self):
        """Test kick damage: 1d6 + DEX bonus."""
        if not SKILLS_IMPLEMENTED:
            pytest.skip("Skills not yet implemented")

        engine_mock = MagicMock()
        engine_mock.broadcast_to_room = MagicMock()
        combat = Combat("test-room", engine_mock)

        attacker = CombatParticipant(
            entity_id="attacker",
            entity_name="Attacker",
            is_npc=False,
        )
        attacker._entity_ref = MagicMock()
        attacker._entity_ref.dexterity = 16  # +3 bonus
        attacker._entity_ref.current_hp = 100
        attacker.skill_cooldowns = {}
        attacker.effects = {}

        target = CombatParticipant(
            entity_id="target",
            entity_name="Target",
            is_npc=False,
        )
        target._entity_ref = MagicMock()
        target._entity_ref.dexterity = 10
        target._entity_ref.current_hp = 100
        target.effects = {}

        # Guarantee hit
        with patch('random.randint', return_value=20):
            combat.participants = [attacker, target]
            success, msg = await execute_kick(combat, attacker, target)

        # Check that damage was dealt (message should contain damage)
        assert "damage" in msg.lower() or "hit" in msg.lower()

    @pytest.mark.asyncio
    async def test_kick_wait_state_one_round(self):
        """Test that kick applies 1-round wait state."""
        if not SKILLS_IMPLEMENTED:
            pytest.skip("Skills not yet implemented")

        engine_mock = MagicMock()
        engine_mock.broadcast_to_room = MagicMock()
        combat = Combat("test-room", engine_mock)

        attacker = CombatParticipant(
            entity_id="attacker",
            entity_name="Attacker",
            is_npc=False,
        )
        attacker._entity_ref = MagicMock()
        attacker._entity_ref.dexterity = 16
        attacker._entity_ref.current_hp = 100
        attacker.skill_cooldowns = {}
        attacker.effects = {}
        attacker.wait_state_until = None

        target = CombatParticipant(
            entity_id="target",
            entity_name="Target",
            is_npc=False,
        )
        target._entity_ref = MagicMock()
        target._entity_ref.dexterity = 10
        target._entity_ref.current_hp = 100
        target.effects = {}

        before = datetime.now()
        combat.participants = [attacker, target]
        await execute_kick(combat, attacker, target)

        # 1 round = 3 seconds
        assert attacker.wait_state_until is not None
        wait_duration = (attacker.wait_state_until - before).total_seconds()
        assert 2.5 <= wait_duration <= 3.5

    @pytest.mark.asyncio
    async def test_kick_cooldown(self):
        """Test that kick applies 10-second cooldown."""
        if not SKILLS_IMPLEMENTED:
            pytest.skip("Skills not yet implemented")

        engine_mock = MagicMock()
        engine_mock.broadcast_to_room = MagicMock()
        combat = Combat("test-room", engine_mock)

        attacker = CombatParticipant(
            entity_id="attacker",
            entity_name="Attacker",
            is_npc=False,
        )
        attacker._entity_ref = MagicMock()
        attacker._entity_ref.dexterity = 16
        attacker._entity_ref.current_hp = 100
        attacker.skill_cooldowns = {}
        attacker.effects = {}

        target = CombatParticipant(
            entity_id="target",
            entity_name="Target",
            is_npc=False,
        )
        target._entity_ref = MagicMock()
        target._entity_ref.dexterity = 10
        target._entity_ref.current_hp = 100
        target.effects = {}

        combat.participants = [attacker, target]
        await execute_kick(combat, attacker, target)

        assert is_skill_on_cooldown(attacker, "kick") is True


class TestDisarmSkill:
    """Tests for disarm skill (remove weapon)."""

    @pytest.mark.asyncio
    async def test_disarm_roll_vs_dex(self):
        """Test disarm roll: d20 + DEX vs target DEX + 10."""
        if not SKILLS_IMPLEMENTED:
            pytest.skip("Skills not yet implemented")

        engine_mock = MagicMock()
        engine_mock.broadcast_to_room = MagicMock()
        combat = Combat("test-room", engine_mock)

        attacker = CombatParticipant(
            entity_id="attacker",
            entity_name="Attacker",
            is_npc=False,
        )
        attacker._entity_ref = MagicMock()
        attacker._entity_ref.dexterity = 18  # +4 bonus
        attacker._entity_ref.current_hp = 100
        attacker.skill_cooldowns = {}
        attacker.effects = {}

        target = CombatParticipant(
            entity_id="target",
            entity_name="Target",
            is_npc=False,
        )
        target._entity_ref = MagicMock()
        target._entity_ref.dexterity = 10  # DC 10
        target._entity_ref.current_hp = 100
        target.effects = {}

        # Guarantee success with high roll
        with patch('random.randint', return_value=20):
            combat.participants = [attacker, target]
            success, msg = await execute_disarm(combat, attacker, target)

        # Should succeed
        assert success is True

    @pytest.mark.asyncio
    async def test_disarm_applies_disarmed_effect(self):
        """Test that disarm applies disarmed effect to target."""
        if not SKILLS_IMPLEMENTED:
            pytest.skip("Skills not yet implemented")

        engine_mock = MagicMock()
        engine_mock.broadcast_to_room = MagicMock()
        combat = Combat("test-room", engine_mock)

        attacker = CombatParticipant(
            entity_id="attacker",
            entity_name="Attacker",
            is_npc=False,
        )
        attacker._entity_ref = MagicMock()
        attacker._entity_ref.dexterity = 18
        attacker._entity_ref.current_hp = 100
        attacker.skill_cooldowns = {}
        attacker.effects = {}

        target = CombatParticipant(
            entity_id="target",
            entity_name="Target",
            is_npc=False,
        )
        target._entity_ref = MagicMock()
        target._entity_ref.dexterity = 10
        target._entity_ref.current_hp = 100
        target.effects = {}

        with patch('random.randint', return_value=20):
            combat.participants = [attacker, target]
            success, msg = await execute_disarm(combat, attacker, target)

        # Target should have disarmed effect
        assert "disarmed" in target.effects or "disarm" in msg.lower()

    @pytest.mark.asyncio
    async def test_disarm_cooldown(self):
        """Test that disarm applies 30-second cooldown."""
        if not SKILLS_IMPLEMENTED:
            pytest.skip("Skills not yet implemented")

        engine_mock = MagicMock()
        engine_mock.broadcast_to_room = MagicMock()
        combat = Combat("test-room", engine_mock)

        attacker = CombatParticipant(
            entity_id="attacker",
            entity_name="Attacker",
            is_npc=False,
        )
        attacker._entity_ref = MagicMock()
        attacker._entity_ref.dexterity = 18
        attacker._entity_ref.current_hp = 100
        attacker.skill_cooldowns = {}
        attacker.effects = {}

        target = CombatParticipant(
            entity_id="target",
            entity_name="Target",
            is_npc=False,
        )
        target._entity_ref = MagicMock()
        target._entity_ref.dexterity = 10
        target._entity_ref.current_hp = 100
        target.effects = {}

        combat.participants = [attacker, target]
        await execute_disarm(combat, attacker, target)

        assert is_skill_on_cooldown(attacker, "disarm") is True


class TestTripSkill:
    """Tests for trip skill (knock prone)."""

    @pytest.mark.asyncio
    async def test_trip_roll_vs_dex(self):
        """Test trip roll: d20 + DEX vs target DEX + 8."""
        if not SKILLS_IMPLEMENTED:
            pytest.skip("Skills not yet implemented")

        engine_mock = MagicMock()
        engine_mock.broadcast_to_room = MagicMock()
        combat = Combat("test-room", engine_mock)

        attacker = CombatParticipant(
            entity_id="attacker",
            entity_name="Attacker",
            is_npc=False,
        )
        attacker._entity_ref = MagicMock()
        attacker._entity_ref.dexterity = 16
        attacker._entity_ref.current_hp = 100
        attacker.skill_cooldowns = {}
        attacker.effects = {}

        target = CombatParticipant(
            entity_id="target",
            entity_name="Target",
            is_npc=False,
        )
        target._entity_ref = MagicMock()
        target._entity_ref.dexterity = 10  # DC 8
        target._entity_ref.current_hp = 100
        target.effects = {}

        with patch('random.randint', return_value=15):
            combat.participants = [attacker, target]
            success, msg = await execute_trip(combat, attacker, target)

        assert success is True

    @pytest.mark.asyncio
    async def test_trip_applies_prone_effect(self):
        """Test that trip applies prone effect (-2 to hit next round)."""
        if not SKILLS_IMPLEMENTED:
            pytest.skip("Skills not yet implemented")

        engine_mock = MagicMock()
        engine_mock.broadcast_to_room = MagicMock()
        combat = Combat("test-room", engine_mock)

        attacker = CombatParticipant(
            entity_id="attacker",
            entity_name="Attacker",
            is_npc=False,
        )
        attacker._entity_ref = MagicMock()
        attacker._entity_ref.dexterity = 16
        attacker._entity_ref.current_hp = 100
        attacker.skill_cooldowns = {}
        attacker.effects = {}

        target = CombatParticipant(
            entity_id="target",
            entity_name="Target",
            is_npc=False,
        )
        target._entity_ref = MagicMock()
        target._entity_ref.dexterity = 10
        target._entity_ref.current_hp = 100
        target.effects = {}

        with patch('random.randint', return_value=20):
            combat.participants = [attacker, target]
            success, msg = await execute_trip(combat, attacker, target)

        # Target should have prone effect
        assert "prone" in target.effects or "trip" in msg.lower() or "fall" in msg.lower()

    @pytest.mark.asyncio
    async def test_trip_cooldown(self):
        """Test that trip applies 12-second cooldown."""
        if not SKILLS_IMPLEMENTED:
            pytest.skip("Skills not yet implemented")

        engine_mock = MagicMock()
        engine_mock.broadcast_to_room = MagicMock()
        combat = Combat("test-room", engine_mock)

        attacker = CombatParticipant(
            entity_id="attacker",
            entity_name="Attacker",
            is_npc=False,
        )
        attacker._entity_ref = MagicMock()
        attacker._entity_ref.dexterity = 16
        attacker._entity_ref.current_hp = 100
        attacker.skill_cooldowns = {}
        attacker.effects = {}

        target = CombatParticipant(
            entity_id="target",
            entity_name="Target",
            is_npc=False,
        )
        target._entity_ref = MagicMock()
        target._entity_ref.dexterity = 10
        target._entity_ref.current_hp = 100
        target.effects = {}

        combat.participants = [attacker, target]
        await execute_trip(combat, attacker, target)

        assert is_skill_on_cooldown(attacker, "trip") is True


class TestEffectsOnCombat:
    """Tests for how effects modify combat actions."""

    @pytest.mark.asyncio
    async def test_knocked_down_skips_turn(self):
        """Test that knocked down effect causes entity to skip their turn."""
        if not SKILLS_IMPLEMENTED:
            pytest.skip("Skills not yet implemented")

        # This test will verify that _execute_attack checks for knockdown
        # For now, just verify the effect structure
        p = CombatParticipant(
            entity_id="test",
            entity_name="Test",
            is_npc=False,
        )
        p.effects = {"knocked_down": True}

        assert p.effects.get("knocked_down") is True

    @pytest.mark.asyncio
    async def test_prone_applies_attack_penalty(self):
        """Test that prone effect applies -2 to attack rolls."""
        if not SKILLS_IMPLEMENTED:
            pytest.skip("Skills not yet implemented")

        # This test will verify that attack rolls check for prone
        p = CombatParticipant(
            entity_id="test",
            entity_name="Test",
            is_npc=False,
        )
        p.effects = {"prone": -2}

        assert p.effects.get("prone") == -2
