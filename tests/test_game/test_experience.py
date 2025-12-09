"""Tests for experience and XP calculation system."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from waystone.database.models import Character
from waystone.game.systems.experience import (
    XP_COMBAT_KILL_BASE,
    XP_EXPLORATION_NEW_ROOM,
    XP_FIRST_LOGIN,
    XP_QUEST_COMPLETE_BASE,
    award_xp,
    xp_for_level,
    xp_for_next_level,
    xp_progress,
)


class TestXPCalculations:
    """Test XP calculation functions."""

    def test_xp_for_level_1(self):
        """Level 1 requires 0 XP (starting level)."""
        assert xp_for_level(1) == 0

    def test_xp_for_level_2(self):
        """Level 2 requires 100 XP total."""
        # Level 2 = (2-1) * 100 * (2-1) = 1 * 100 * 1 = 100
        assert xp_for_level(2) == 100

    def test_xp_for_level_3(self):
        """Level 3 requires 400 XP total (100 + 300)."""
        # Level 2 = 100
        # Level 3 = 100 + (2 * 100 * 2) = 100 + 400 = 500? No...
        # Actually: level 2 needs 100, level 3 needs 300 more
        # Total for level 3 = 100 + 300 = 400
        # Formula per level: (level-1) * 100 * (level-1)
        # Level 2: 1*100*1 = 100
        # Level 3: 2*100*2 = 400
        # Cumulative: 100 + 400 = 500? Let me recalculate...
        # Actually the XP needed to go from N to N+1 is: N * 100 * N
        # So 1->2 = 1*100*1 = 100
        # 2->3 = 2*100*2 = 400? No, that's too much
        # Let me check the docstring again: level * 100 * level is the formula
        # For level 2: need 100 total
        # For level 3: need 400 total (so 300 more from level 2)
        assert xp_for_level(3) == 400

    def test_xp_for_level_4(self):
        """Level 4 requires 1000 XP total."""
        # From docstring: Level 3→4: 600 XP
        # Total: 100 + 300 + 600 = 1000
        assert xp_for_level(4) == 1000

    def test_xp_for_next_level(self):
        """Test XP needed for next level."""
        # Level 1->2: 100*1*2/2 = 100
        assert xp_for_next_level(1) == 100

        # Level 2->3: 100*2*3/2 = 300
        assert xp_for_next_level(2) == 300

        # Level 3->4: 100*3*4/2 = 600
        assert xp_for_next_level(3) == 600

        # Level 4->5: 100*4*5/2 = 1000
        assert xp_for_next_level(4) == 1000

    def test_xp_progress_level_1_no_xp(self):
        """Character at level 1 with no XP."""
        char = Character(
            user_id="00000000-0000-0000-0000-000000000000",
            name="Test",
            background="Scholar",
            current_room_id="test",
            level=1,
            experience=0,
        )

        current, needed = xp_progress(char)
        assert current == 0
        assert needed == 100  # Need 100 XP for level 2

    def test_xp_progress_level_1_partial(self):
        """Character at level 1 with partial XP."""
        char = Character(
            user_id="00000000-0000-0000-0000-000000000000",
            name="Test",
            background="Scholar",
            current_room_id="test",
            level=1,
            experience=50,
        )

        current, needed = xp_progress(char)
        assert current == 50
        assert needed == 100

    def test_xp_progress_level_2(self):
        """Character at level 2."""
        char = Character(
            user_id="00000000-0000-0000-0000-000000000000",
            name="Test",
            background="Scholar",
            current_room_id="test",
            level=2,
            experience=250,  # 100 for level 2, 150 toward level 3
        )

        current, needed = xp_progress(char)
        # XP for level 2 = 100
        # XP for level 3 = 400
        # Progress within level = 250 - 100 = 150
        # Needed for level = 400 - 100 = 300
        assert current == 150
        assert needed == 300

    def test_xp_constants_defined(self):
        """Verify XP source constants are defined."""
        assert XP_EXPLORATION_NEW_ROOM == 25
        assert XP_FIRST_LOGIN == 100
        assert XP_COMBAT_KILL_BASE == 50
        assert XP_QUEST_COMPLETE_BASE == 100


class TestAwardXP:
    """Test awarding XP to characters."""

    @pytest.mark.asyncio
    async def test_award_xp_no_levelup(self, db_session: AsyncSession, test_character):
        """Award XP without triggering level-up."""
        char_id = test_character.id
        initial_xp = test_character.experience
        initial_level = test_character.level

        # Award 50 XP (not enough to level up from level 1)
        new_xp, leveled_up = await award_xp(
            char_id,
            50,
            "test_source",
            session=db_session,
        )

        assert new_xp == initial_xp + 50
        assert not leveled_up

        # Refresh character from DB
        await db_session.refresh(test_character)
        assert test_character.experience == 50
        assert test_character.level == initial_level

    @pytest.mark.asyncio
    async def test_award_xp_single_levelup(self, db_session: AsyncSession, test_character):
        """Award XP that triggers a single level-up."""
        char_id = test_character.id

        # Award 100 XP (exact amount for level 2)
        new_xp, leveled_up = await award_xp(
            char_id,
            100,
            "first_login",
            session=db_session,
        )

        assert new_xp == 100
        assert leveled_up

        # Refresh character from DB
        await db_session.refresh(test_character)
        assert test_character.level == 2
        assert test_character.experience == 100
        assert test_character.attribute_points == 1  # Gained 1 point
        assert test_character.current_hp == test_character.max_hp  # Healed to full

    @pytest.mark.asyncio
    async def test_award_xp_multiple_levelups(self, db_session: AsyncSession, test_character):
        """Award enough XP to trigger multiple level-ups."""
        char_id = test_character.id

        # Award 1000 XP (should reach level 4)
        new_xp, leveled_up = await award_xp(
            char_id,
            1000,
            "quest_complete",
            session=db_session,
        )

        assert new_xp == 1000
        assert leveled_up

        # Refresh character from DB
        await db_session.refresh(test_character)
        # Level 2 at 100 XP, Level 3 at 400 XP, Level 4 at 1000 XP
        assert test_character.level == 4
        assert test_character.attribute_points == 3  # Gained 1 per level (3 levels)
        assert test_character.current_hp == test_character.max_hp

    @pytest.mark.asyncio
    async def test_award_xp_partial_progress(self, db_session: AsyncSession, test_character):
        """Award XP multiple times with partial progress."""
        char_id = test_character.id

        # Award 50 XP
        new_xp, leveled_up = await award_xp(char_id, 50, "exploration", session=db_session)
        assert new_xp == 50
        assert not leveled_up

        await db_session.refresh(test_character)
        assert test_character.level == 1

        # Award another 50 XP (now at 100, should level up)
        new_xp, leveled_up = await award_xp(char_id, 50, "combat", session=db_session)
        assert new_xp == 100
        assert leveled_up

        await db_session.refresh(test_character)
        assert test_character.level == 2

    @pytest.mark.asyncio
    async def test_award_xp_nonexistent_character(self, db_session: AsyncSession):
        """Awarding XP to non-existent character raises error."""
        import uuid

        fake_id = uuid.uuid4()

        with pytest.raises(ValueError, match="Character with ID .* not found"):
            await award_xp(fake_id, 100, "test", session=db_session)

    @pytest.mark.asyncio
    async def test_award_xp_realistic_combat_scenario(
        self, db_session: AsyncSession, test_character
    ):
        """Test realistic combat XP award."""
        char_id = test_character.id

        # Kill enemy of level 1: 50 * 1 = 50 XP
        new_xp, leveled_up = await award_xp(
            char_id,
            XP_COMBAT_KILL_BASE * 1,
            "combat_kill_level_1",
            session=db_session,
        )

        assert new_xp == 50
        assert not leveled_up

        # Kill another level 1 enemy: +50 = 100 total
        new_xp, leveled_up = await award_xp(
            char_id,
            XP_COMBAT_KILL_BASE * 1,
            "combat_kill_level_1",
            session=db_session,
        )

        assert new_xp == 100
        assert leveled_up

        await db_session.refresh(test_character)
        assert test_character.level == 2

    @pytest.mark.asyncio
    async def test_award_xp_exploration_scenario(self, db_session: AsyncSession, test_character):
        """Test exploration XP awards."""
        char_id = test_character.id

        # Explore 4 new rooms: 4 * 25 = 100 XP
        for i in range(4):
            new_xp, leveled_up = await award_xp(
                char_id,
                XP_EXPLORATION_NEW_ROOM,
                f"exploration_room_{i}",
                session=db_session,
            )

        assert new_xp == 100
        await db_session.refresh(test_character)
        assert test_character.level == 2
