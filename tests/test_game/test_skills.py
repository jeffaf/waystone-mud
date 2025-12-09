"""Tests for the skills system."""

import pytest

from waystone.game.character.skills import (
    format_skill_bar,
    gain_skill_xp,
    get_all_skills,
    get_skill_bonus,
    get_skill_info,
    get_skill_rank_name,
    get_xp_progress,
    load_skill_definitions,
    xp_for_rank,
)


class TestSkillRanks:
    """Test skill rank calculations and names."""

    def test_get_skill_rank_name(self):
        """Test getting rank names."""
        assert get_skill_rank_name(0) == "Untrained"
        assert get_skill_rank_name(1) == "Novice"
        assert get_skill_rank_name(2) == "Novice"
        assert get_skill_rank_name(3) == "Apprentice"
        assert get_skill_rank_name(4) == "Apprentice"
        assert get_skill_rank_name(5) == "Journeyman"
        assert get_skill_rank_name(6) == "Journeyman"
        assert get_skill_rank_name(7) == "Expert"
        assert get_skill_rank_name(8) == "Expert"
        assert get_skill_rank_name(9) == "Master"
        assert get_skill_rank_name(10) == "Grandmaster"

    def test_get_skill_rank_name_edge_cases(self):
        """Test rank name edge cases."""
        assert get_skill_rank_name(-1) == "Untrained"
        assert get_skill_rank_name(11) == "Grandmaster"
        assert get_skill_rank_name(100) == "Grandmaster"

    def test_xp_for_rank(self):
        """Test XP calculation for ranks."""
        assert xp_for_rank(0) == 0
        assert xp_for_rank(1) == 100  # Rank 1 needs 100 XP
        assert xp_for_rank(2) == 200  # Rank 2 needs 200 XP
        assert xp_for_rank(5) == 500  # Rank 5 needs 500 XP
        assert xp_for_rank(10) == 1000  # Rank 10 needs 1000 XP

    def test_get_skill_bonus(self):
        """Test skill bonus calculation."""
        assert get_skill_bonus(0) == 0
        assert get_skill_bonus(1) == 1
        assert get_skill_bonus(5) == 5
        assert get_skill_bonus(10) == 10


class TestSkillXP:
    """Test XP gain and rank-up mechanics."""

    @pytest.mark.asyncio
    async def test_gain_skill_xp_new_skill(self, test_character, db_session):
        """Test gaining XP in a new skill."""
        # Character starts with no skills
        assert test_character.skills == {}

        # Gain 50 XP in swordplay
        new_xp, ranked_up = await gain_skill_xp(test_character, "swordplay", 50, db_session)

        assert new_xp == 50
        assert ranked_up is False
        assert "swordplay" in test_character.skills
        assert test_character.skills["swordplay"]["rank"] == 0
        assert test_character.skills["swordplay"]["xp"] == 50

    @pytest.mark.asyncio
    async def test_gain_skill_xp_rank_up(self, test_character, db_session):
        """Test ranking up a skill."""
        # Character starts with no skills
        assert test_character.skills == {}

        # Gain 100 XP to reach rank 1
        new_xp, ranked_up = await gain_skill_xp(test_character, "swordplay", 100, db_session)

        assert new_xp == 100
        assert ranked_up is True
        assert test_character.skills["swordplay"]["rank"] == 1
        assert test_character.skills["swordplay"]["xp"] == 100

    @pytest.mark.asyncio
    async def test_gain_skill_xp_multiple_ranks(self, test_character, db_session):
        """Test gaining XP across multiple training sessions."""
        # Start with no skills
        assert test_character.skills == {}

        # First training: 50 XP (rank 0, no rank-up)
        new_xp, ranked_up = await gain_skill_xp(test_character, "archery", 50, db_session)
        assert new_xp == 50
        assert ranked_up is False
        assert test_character.skills["archery"]["rank"] == 0

        # Second training: 50 more XP (total 100, rank-up to 1)
        new_xp, ranked_up = await gain_skill_xp(test_character, "archery", 50, db_session)
        assert new_xp == 100
        assert ranked_up is True
        assert test_character.skills["archery"]["rank"] == 1

        # Third training: 100 more XP (total 200, no rank-up yet)
        new_xp, ranked_up = await gain_skill_xp(test_character, "archery", 100, db_session)
        assert new_xp == 200
        assert ranked_up is True  # Rank up to 2
        assert test_character.skills["archery"]["rank"] == 2

    @pytest.mark.asyncio
    async def test_gain_skill_xp_max_rank(self, test_character, db_session):
        """Test that skills don't rank up past max rank."""
        # Set character to max rank
        test_character.skills = {"sympathy": {"rank": 10, "xp": 1000}}

        # Try to gain more XP
        new_xp, ranked_up = await gain_skill_xp(test_character, "sympathy", 100, db_session)

        assert new_xp == 1100  # XP still increases
        assert ranked_up is False  # But no rank-up
        assert test_character.skills["sympathy"]["rank"] == 10  # Still max rank

    @pytest.mark.asyncio
    async def test_multiple_skills(self, test_character, db_session):
        """Test managing multiple skills on one character."""
        # Gain XP in multiple skills
        await gain_skill_xp(test_character, "swordplay", 100, db_session)
        await gain_skill_xp(test_character, "sympathy", 150, db_session)
        await gain_skill_xp(test_character, "music", 75, db_session)

        # Verify all skills are tracked
        assert "swordplay" in test_character.skills
        assert "sympathy" in test_character.skills
        assert "music" in test_character.skills

        # Verify ranks
        assert test_character.skills["swordplay"]["rank"] == 1  # 100 XP = rank 1
        assert test_character.skills["sympathy"]["rank"] == 1  # 150 XP = rank 1
        assert test_character.skills["music"]["rank"] == 0  # 75 XP = still rank 0


class TestSkillDefinitions:
    """Test skill definition loading and access."""

    def test_load_skill_definitions(self):
        """Test loading skill definitions from YAML."""
        definitions = load_skill_definitions()

        # Check categories exist
        assert "combat" in definitions
        assert "magic" in definitions
        assert "practical" in definitions

        # Check some skills exist
        assert "swordplay" in definitions["combat"]
        assert "sympathy" in definitions["magic"]
        assert "music" in definitions["practical"]

    def test_get_all_skills(self):
        """Test getting all skill names."""
        skills = get_all_skills()

        # Should be a sorted list
        assert isinstance(skills, list)
        assert len(skills) > 0

        # Check for specific skills
        assert "swordplay" in skills
        assert "sympathy" in skills
        assert "music" in skills

        # Should be sorted
        assert skills == sorted(skills)

    def test_get_skill_info(self):
        """Test getting info for a specific skill."""
        # Test valid skill
        swordplay_info = get_skill_info("swordplay")
        assert swordplay_info is not None
        assert swordplay_info["name"] == "Swordplay"
        assert "description" in swordplay_info
        assert swordplay_info["attribute"] == "dexterity"

        # Test magic skill with rare flag
        sympathy_info = get_skill_info("sympathy")
        assert sympathy_info is not None
        assert sympathy_info["name"] == "Sympathy"
        assert sympathy_info.get("rare") is True

        # Test invalid skill
        invalid_info = get_skill_info("invalid_skill")
        assert invalid_info is None


class TestSkillProgress:
    """Test XP progress calculation and display."""

    def test_get_xp_progress_rank_0(self):
        """Test XP progress for rank 0."""
        current_xp, xp_needed = get_xp_progress(50, 0)
        assert current_xp == 50
        assert xp_needed == 100  # Need 100 XP to reach rank 1

    def test_get_xp_progress_rank_5(self):
        """Test XP progress for rank 5."""
        current_xp, xp_needed = get_xp_progress(500, 5)
        assert current_xp == 500
        assert xp_needed == 600  # Need 600 XP to reach rank 6

    def test_get_xp_progress_max_rank(self):
        """Test XP progress at max rank."""
        current_xp, xp_needed = get_xp_progress(1000, 10)
        assert current_xp == 1000
        assert xp_needed == 1000  # At max rank

    def test_format_skill_bar_empty(self):
        """Test formatting empty progress bar."""
        bar = format_skill_bar(0, 100)
        assert bar == "░░░░░░░░░░"
        assert len(bar) == 10

    def test_format_skill_bar_half(self):
        """Test formatting half-full progress bar."""
        bar = format_skill_bar(50, 100)
        assert bar == "█████░░░░░"
        assert len(bar) == 10

    def test_format_skill_bar_full(self):
        """Test formatting full progress bar."""
        bar = format_skill_bar(100, 100)
        assert bar == "██████████"
        assert len(bar) == 10

    def test_format_skill_bar_custom_width(self):
        """Test formatting progress bar with custom width."""
        bar = format_skill_bar(50, 100, width=20)
        assert len(bar) == 20
        assert bar.count("█") == 10
        assert bar.count("░") == 10

    def test_format_skill_bar_overfill(self):
        """Test formatting progress bar when XP exceeds needed."""
        bar = format_skill_bar(150, 100)
        assert bar == "██████████"  # Should cap at full
        assert len(bar) == 10


class TestSkillIntegration:
    """Integration tests for the complete skills system."""

    @pytest.mark.asyncio
    async def test_complete_skill_progression(self, test_character, db_session):
        """Test a complete skill progression from rank 0 to 3."""
        skill_name = "swordplay"

        # Start at rank 0
        assert skill_name not in test_character.skills

        # Gain 100 XP -> Rank 1
        new_xp, ranked_up = await gain_skill_xp(test_character, skill_name, 100, db_session)
        assert ranked_up is True
        assert test_character.skills[skill_name]["rank"] == 1
        assert get_skill_rank_name(1) == "Novice"
        assert get_skill_bonus(1) == 1

        # Gain 100 more XP (total 200) -> Rank 2
        new_xp, ranked_up = await gain_skill_xp(test_character, skill_name, 100, db_session)
        assert ranked_up is True
        assert test_character.skills[skill_name]["rank"] == 2
        assert get_skill_rank_name(2) == "Novice"
        assert get_skill_bonus(2) == 2

        # Gain 100 more XP (total 300) -> Rank 3
        new_xp, ranked_up = await gain_skill_xp(test_character, skill_name, 100, db_session)
        assert ranked_up is True
        assert test_character.skills[skill_name]["rank"] == 3
        assert get_skill_rank_name(3) == "Apprentice"
        assert get_skill_bonus(3) == 3

        # Total XP should be 300
        assert test_character.skills[skill_name]["xp"] == 300

    @pytest.mark.asyncio
    async def test_incremental_training(self, test_character, db_session):
        """Test incremental XP gains like from training command."""
        skill_name = "music"

        # Simulate multiple training sessions with small XP gains
        for _ in range(10):
            await gain_skill_xp(test_character, skill_name, 25, db_session)

        # After 10 sessions of 25 XP each = 250 XP total
        assert test_character.skills[skill_name]["xp"] == 250
        # Should be rank 2 (need 100 for rank 1, 200 for rank 2)
        assert test_character.skills[skill_name]["rank"] == 2

    @pytest.mark.asyncio
    async def test_character_with_mixed_skills(self, test_character, db_session):
        """Test a character with various skill levels."""
        # Create a character with diverse skills
        # 350 XP = Rank 3 (100 for rank 1, 200 for rank 2, 300 for rank 3)
        await gain_skill_xp(test_character, "swordplay", 350, db_session)
        await gain_skill_xp(test_character, "sympathy", 100, db_session)  # Rank 1
        await gain_skill_xp(test_character, "music", 75, db_session)  # Rank 0
        # 600 XP = Rank 6 (100, 200, 300, 400, 500, 600)
        await gain_skill_xp(test_character, "stealth", 600, db_session)

        # Verify all skills
        assert test_character.skills["swordplay"]["rank"] == 3
        assert test_character.skills["sympathy"]["rank"] == 1
        assert test_character.skills["music"]["rank"] == 0
        assert test_character.skills["stealth"]["rank"] == 6

        # Verify skill bonuses
        assert get_skill_bonus(test_character.skills["swordplay"]["rank"]) == 3
        assert get_skill_bonus(test_character.skills["sympathy"]["rank"]) == 1
        assert get_skill_bonus(test_character.skills["music"]["rank"]) == 0
        assert get_skill_bonus(test_character.skills["stealth"]["rank"]) == 6
