"""Tests for the death and respawn system."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from waystone.game.systems.death import (
    NPCDeathInfo,
    PlayerDeathInfo,
    check_respawns,
    clear_respawn_queue,
    get_pending_respawns,
    handle_npc_death,
    handle_player_death,
)


class TestNPCDeathInfo:
    """Test NPCDeathInfo dataclass."""

    def test_npc_death_info_creation(self):
        """Test creating NPCDeathInfo."""
        death_time = datetime.now()
        info = NPCDeathInfo(
            npc_id="bandit_1",
            npc_name="a scrappy bandit",
            level=2,
            original_room_id="forest",
            death_time=death_time,
            respawn_time=300,
            max_hp=30,
            attributes={"strength": 12, "dexterity": 14},
            loot_table_id="bandit_loot",
            behavior="aggressive",
        )

        assert info.npc_id == "bandit_1"
        assert info.npc_name == "a scrappy bandit"
        assert info.level == 2
        assert info.original_room_id == "forest"
        assert info.death_time == death_time
        assert info.respawn_time == 300
        assert info.max_hp == 30
        assert info.loot_table_id == "bandit_loot"


class TestPlayerDeathInfo:
    """Test PlayerDeathInfo dataclass."""

    def test_player_death_info_creation(self):
        """Test creating PlayerDeathInfo."""
        char_id = uuid4()
        weakened_until = datetime.now() + timedelta(minutes=5)

        info = PlayerDeathInfo(
            character_id=char_id,
            death_location="dark_forest",
            xp_lost=50,
            weakened_until=weakened_until,
        )

        assert info.character_id == char_id
        assert info.death_location == "dark_forest"
        assert info.xp_lost == 50
        assert info.weakened_until == weakened_until


class TestHandleNPCDeath:
    """Test NPC death handling."""

    @pytest.mark.asyncio
    async def test_handle_npc_death_without_killer(self):
        """Test NPC death with no killer (environmental death)."""
        engine = MagicMock()
        engine.character_to_session = {}
        engine.broadcast_to_room = MagicMock()

        await handle_npc_death(
            npc_id="wolf_1",
            npc_name="a grey wolf",
            npc_level=1,
            room_id="forest",
            killer_id=None,
            engine=engine,
            loot_table_id=None,
            respawn_time=0,
        )

        # Should not crash, no XP awarded, no loot
        engine.broadcast_to_room.assert_not_called()

    @pytest.mark.asyncio
    @patch("waystone.game.systems.death.award_xp")
    @patch("waystone.game.systems.death.get_session")
    async def test_handle_npc_death_with_xp_award(self, mock_session, mock_award_xp):
        """Test NPC death awards XP to killer."""
        # Setup mocks
        killer_id = str(uuid4())
        mock_award_xp.return_value = (150, False)

        mock_character = MagicMock()
        mock_character.level = 2

        mock_db_session = AsyncMock()
        mock_db_session.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_db_session.__aexit__ = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_character
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        mock_session.return_value = mock_db_session

        engine = MagicMock()
        engine.character_to_session = {}
        engine.broadcast_to_room = MagicMock()

        await handle_npc_death(
            npc_id="bandit_1",
            npc_name="a scrappy bandit",
            npc_level=2,
            room_id="road",
            killer_id=killer_id,
            engine=engine,
            loot_table_id=None,
            respawn_time=0,
        )

        # Verify XP was awarded (50 * level 2 = 100 XP)
        mock_award_xp.assert_called_once()
        call_args = mock_award_xp.call_args
        assert call_args[1]["amount"] == 100

    @pytest.mark.asyncio
    @patch("waystone.game.systems.death.generate_loot")
    @patch("waystone.game.systems.death.drop_loot_to_room")
    async def test_handle_npc_death_with_loot(self, mock_drop_loot, mock_gen_loot):
        """Test NPC death generates and drops loot."""
        # Setup mocks
        mock_gen_loot.return_value = [("dagger", 1), ("gold", 15)]
        mock_drop_loot.return_value = [MagicMock()]

        engine = MagicMock()
        engine.character_to_session = {}
        engine.broadcast_to_room = MagicMock()

        await handle_npc_death(
            npc_id="bandit_1",
            npc_name="a scrappy bandit",
            npc_level=2,
            room_id="road",
            killer_id=None,
            engine=engine,
            loot_table_id="bandit_loot",
            respawn_time=0,
        )

        # Verify loot generation and drop
        mock_gen_loot.assert_called_once_with("bandit_loot")
        mock_drop_loot.assert_called_once()
        engine.broadcast_to_room.assert_called()

    @pytest.mark.asyncio
    async def test_handle_npc_death_schedules_respawn(self):
        """Test NPC death with respawn time schedules respawn."""
        engine = MagicMock()
        engine.character_to_session = {}
        engine.broadcast_to_room = MagicMock()

        # Clear any previous respawns
        clear_respawn_queue()

        await handle_npc_death(
            npc_id="wolf_1",
            npc_name="a grey wolf",
            npc_level=1,
            room_id="forest",
            killer_id=None,
            engine=engine,
            loot_table_id=None,
            respawn_time=180,
            max_hp=20,
            attributes={"strength": 11},
            behavior="aggressive",
        )

        # Verify respawn was scheduled
        pending = get_pending_respawns()
        assert len(pending) == 1
        assert pending[0].npc_id == "wolf_1"
        assert pending[0].respawn_time == 180

        # Cleanup
        clear_respawn_queue()


class TestHandlePlayerDeath:
    """Test player death handling."""

    @pytest.mark.asyncio
    @patch("waystone.game.systems.death.get_session")
    @patch("waystone.game.systems.experience.xp_for_level")
    @patch("waystone.game.systems.experience.xp_for_next_level")
    async def test_handle_player_death_xp_penalty(self, mock_xp_next, mock_xp_level, mock_session):
        """Test player death applies XP penalty."""
        # Setup mocks
        char_id = uuid4()
        mock_character = MagicMock()
        mock_character.id = char_id
        mock_character.name = "TestChar"
        mock_character.level = 2
        mock_character.experience = 200
        mock_character.current_room_id = "dark_forest"

        mock_xp_level.return_value = 100  # XP for level 2
        mock_xp_next.return_value = 300  # XP needed for next level

        mock_db_session = AsyncMock()
        mock_db_session.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_db_session.__aexit__ = AsyncMock()
        mock_db_session.commit = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_character
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        mock_session.return_value = mock_db_session

        engine = MagicMock()
        engine.world = {
            "dark_forest": MagicMock(),
            "university_courtyard": MagicMock(),
        }
        engine.character_to_session = {}
        engine.broadcast_to_room = MagicMock()

        # Execute death
        death_info = await handle_player_death(
            character_id=char_id,
            death_location="dark_forest",
            engine=engine,
            session=mock_db_session,
        )

        # Verify XP loss (10% of 300 = 30 XP)
        assert death_info.xp_lost == 30
        assert mock_character.experience == 170  # 200 - 30

    @pytest.mark.asyncio
    @patch("waystone.game.systems.death.get_session")
    @patch("waystone.game.systems.experience.xp_for_level")
    @patch("waystone.game.systems.experience.xp_for_next_level")
    async def test_handle_player_death_respawn_location(
        self, mock_xp_next, mock_xp_level, mock_session
    ):
        """Test player death moves to respawn location."""
        # Setup mocks
        char_id = uuid4()
        mock_character = MagicMock()
        mock_character.id = char_id
        mock_character.name = "TestChar"
        mock_character.level = 1
        mock_character.experience = 50
        mock_character.current_room_id = "dangerous_place"

        mock_xp_level.return_value = 0
        mock_xp_next.return_value = 100

        mock_db_session = AsyncMock()
        mock_db_session.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_db_session.__aexit__ = AsyncMock()
        mock_db_session.commit = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_character
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        mock_session.return_value = mock_db_session

        old_room = MagicMock()
        new_room = MagicMock()
        new_room.name = "University Main Hall"

        engine = MagicMock()
        engine.world = {
            "dangerous_place": old_room,
            "university_courtyard": new_room,
        }
        engine.character_to_session = {}
        engine.broadcast_to_room = MagicMock()

        # Execute death
        await handle_player_death(
            character_id=char_id,
            death_location="dangerous_place",
            engine=engine,
            session=mock_db_session,
        )

        # Verify respawn location
        assert mock_character.current_room_id == "university_courtyard"
        assert mock_character.current_hp == 1

        # Verify room tracking updated
        old_room.remove_player.assert_called_once_with(str(char_id))
        new_room.add_player.assert_called_once_with(str(char_id))


class TestRespawnChecking:
    """Test respawn checking logic."""

    @pytest.mark.asyncio
    async def test_check_respawns_empty_queue(self):
        """Test checking respawns with empty queue."""
        clear_respawn_queue()
        engine = MagicMock()

        respawned = await check_respawns(engine)
        assert respawned == 0

    @pytest.mark.asyncio
    async def test_check_respawns_not_ready(self):
        """Test NPCs not ready to respawn yet."""
        clear_respawn_queue()
        engine = MagicMock()
        engine.broadcast_to_room = MagicMock()

        # Schedule NPC with future respawn
        await handle_npc_death(
            npc_id="wolf_1",
            npc_name="a grey wolf",
            npc_level=1,
            room_id="forest",
            killer_id=None,
            engine=engine,
            loot_table_id=None,
            respawn_time=3600,  # 1 hour in future
            max_hp=20,
        )

        # Check respawns
        respawned = await check_respawns(engine)
        assert respawned == 0

        # Verify NPC still in queue
        pending = get_pending_respawns()
        assert len(pending) == 1

        clear_respawn_queue()

    @pytest.mark.asyncio
    async def test_check_respawns_ready(self):
        """Test NPCs ready to respawn."""
        clear_respawn_queue()
        engine = MagicMock()
        engine.broadcast_to_room = MagicMock()

        # Manually add NPC that died in the past
        from waystone.game.systems.death import _dead_npcs

        past_death = datetime.now() - timedelta(minutes=10)
        _dead_npcs["wolf_1"] = NPCDeathInfo(
            npc_id="wolf_1",
            npc_name="a grey wolf",
            level=1,
            original_room_id="forest",
            death_time=past_death,
            respawn_time=60,  # 1 minute respawn (already passed)
            max_hp=20,
            attributes={},
            loot_table_id=None,
            behavior="aggressive",
        )

        # Check respawns
        respawned = await check_respawns(engine)
        assert respawned == 1

        # Verify NPC removed from queue
        pending = get_pending_respawns()
        assert len(pending) == 0

        # Verify broadcast was sent
        engine.broadcast_to_room.assert_called_once()

        clear_respawn_queue()


class TestRespawnQueueManagement:
    """Test respawn queue utility functions."""

    def test_get_pending_respawns(self):
        """Test getting list of pending respawns."""
        clear_respawn_queue()

        from waystone.game.systems.death import _dead_npcs

        # Add test NPCs
        _dead_npcs["npc1"] = NPCDeathInfo(
            npc_id="npc1",
            npc_name="NPC 1",
            level=1,
            original_room_id="room1",
            death_time=datetime.now(),
            respawn_time=100,
            max_hp=20,
            attributes={},
            loot_table_id=None,
            behavior="passive",
        )

        pending = get_pending_respawns()
        assert len(pending) == 1
        assert pending[0].npc_id == "npc1"

        clear_respawn_queue()

    def test_clear_respawn_queue(self):
        """Test clearing the respawn queue."""
        from waystone.game.systems.death import _dead_npcs

        # Add test NPC
        _dead_npcs["test"] = NPCDeathInfo(
            npc_id="test",
            npc_name="Test",
            level=1,
            original_room_id="test",
            death_time=datetime.now(),
            respawn_time=100,
            max_hp=20,
            attributes={},
            loot_table_id=None,
            behavior="passive",
        )

        assert len(get_pending_respawns()) == 1

        clear_respawn_queue()

        assert len(get_pending_respawns()) == 0
