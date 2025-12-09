"""Tests for NPC display functionality."""

import pytest
from waystone.game.world.npc_loader import NPCTemplate
from waystone.game.systems.npc_combat import spawn_npc, reset_all_npcs, get_npcs_in_room
from waystone.game.systems.npc_display import (
    get_health_condition,
    get_short_health_status,
    get_item_display_name,
    find_npc_by_keywords,
    group_npcs_by_template,
    get_npc_color,
    format_npc_room_presence,
)


@pytest.fixture(autouse=True)
def reset_npcs():
    """Reset NPCs before each test."""
    reset_all_npcs()
    yield
    reset_all_npcs()


class TestHealthConditions:
    """Test health condition display."""

    def test_perfect_health(self):
        """Test health condition at 100% HP."""
        template = NPCTemplate(
            id="test_npc",
            name="a test creature",
            description="Test",
            max_hp=100,
        )
        npc = spawn_npc(template, "test_room")
        npc.current_hp = 100

        result = get_health_condition(npc)
        assert "perfect health" in result.lower()

    def test_wounded(self):
        """Test health condition at 50% HP."""
        template = NPCTemplate(
            id="test_npc",
            name="a test creature",
            description="Test",
            max_hp=100,
        )
        npc = spawn_npc(template, "test_room")
        npc.current_hp = 50

        result = get_health_condition(npc)
        assert "wounded" in result.lower()

    def test_near_death(self):
        """Test health condition at low HP."""
        template = NPCTemplate(
            id="test_npc",
            name="a test creature",
            description="Test",
            max_hp=100,
        )
        npc = spawn_npc(template, "test_room")
        npc.current_hp = 5

        result = get_health_condition(npc)
        assert "mortally wounded" in result.lower()

    def test_short_health_status_healthy(self):
        """Test short health status for healthy NPC."""
        template = NPCTemplate(
            id="test_npc",
            name="a test creature",
            description="Test",
            max_hp=100,
        )
        npc = spawn_npc(template, "test_room")
        npc.current_hp = 80

        result = get_short_health_status(npc)
        assert result == "looks healthy"

    def test_short_health_status_wounded(self):
        """Test short health status for wounded NPC."""
        template = NPCTemplate(
            id="test_npc",
            name="a test creature",
            description="Test",
            max_hp=100,
        )
        npc = spawn_npc(template, "test_room")
        npc.current_hp = 50

        result = get_short_health_status(npc)
        assert result == "has some wounds"


class TestItemDisplayNames:
    """Test item display name conversion."""

    def test_simple_item(self):
        """Test simple item name conversion."""
        result = get_item_display_name("rusty_sword")
        assert result == "a rusty sword"

    def test_vowel_start(self):
        """Test item starting with vowel gets 'an'."""
        result = get_item_display_name("emerald_ring")
        assert result == "an emerald ring"

    def test_with_existing_article(self):
        """Test item that already has an article."""
        result = get_item_display_name("the_master_sword")
        # "the" is treated as part of the name, so it gets "a" prepended
        assert result == "the master sword"  # 'the_' becomes 'the ', then gets 'a'


class TestKeywordMatching:
    """Test NPC keyword-based search."""

    def test_exact_keyword_match(self):
        """Test finding NPC by exact keyword."""
        template = NPCTemplate(
            id="bandit",
            name="a scrappy bandit",
            description="A bandit",
            keywords=["bandit", "scrappy", "thief"],
        )
        spawn_npc(template, "test_room")

        result = find_npc_by_keywords("test_room", "bandit")
        assert result is not None
        assert result.template_id == "bandit"

    def test_keyword_case_insensitive(self):
        """Test keyword matching is case insensitive."""
        template = NPCTemplate(
            id="bandit",
            name="a scrappy bandit",
            description="A bandit",
            keywords=["bandit", "scrappy"],
        )
        spawn_npc(template, "test_room")

        result = find_npc_by_keywords("test_room", "BANDIT")
        assert result is not None

    def test_name_fallback(self):
        """Test fallback to name matching when no keywords."""
        template = NPCTemplate(
            id="rat",
            name="a giant rat",
            description="A rat",
            keywords=[],
        )
        spawn_npc(template, "test_room")

        result = find_npc_by_keywords("test_room", "rat")
        assert result is not None

    def test_no_match(self):
        """Test no match returns None."""
        template = NPCTemplate(
            id="bandit",
            name="a bandit",
            description="A bandit",
            keywords=["bandit"],
        )
        spawn_npc(template, "test_room")

        result = find_npc_by_keywords("test_room", "dragon")
        assert result is None


class TestNPCGrouping:
    """Test grouping identical NPCs."""

    def test_single_npc(self):
        """Test grouping with single NPC."""
        template = NPCTemplate(
            id="rat",
            name="a giant rat",
            description="A rat",
        )
        npc = spawn_npc(template, "test_room")

        npcs = get_npcs_in_room("test_room")
        groups = group_npcs_by_template(npcs)

        assert len(groups) == 1
        assert "rat" in groups
        assert len(groups["rat"]) == 1

    def test_multiple_identical_npcs(self):
        """Test grouping multiple identical NPCs."""
        template = NPCTemplate(
            id="rat",
            name="a giant rat",
            description="A rat",
        )
        spawn_npc(template, "test_room")
        spawn_npc(template, "test_room")
        spawn_npc(template, "test_room")

        npcs = get_npcs_in_room("test_room")
        groups = group_npcs_by_template(npcs)

        assert len(groups) == 1
        assert len(groups["rat"]) == 3

    def test_multiple_different_npcs(self):
        """Test grouping different NPCs."""
        rat_template = NPCTemplate(
            id="rat",
            name="a giant rat",
            description="A rat",
        )
        bandit_template = NPCTemplate(
            id="bandit",
            name="a bandit",
            description="A bandit",
        )

        spawn_npc(rat_template, "test_room")
        spawn_npc(rat_template, "test_room")
        spawn_npc(bandit_template, "test_room")

        npcs = get_npcs_in_room("test_room")
        groups = group_npcs_by_template(npcs)

        assert len(groups) == 2
        assert len(groups["rat"]) == 2
        assert len(groups["bandit"]) == 1


class TestNPCColor:
    """Test NPC color coding."""

    def test_aggressive_color(self):
        """Test aggressive NPCs are red."""
        template = NPCTemplate(
            id="bandit",
            name="a bandit",
            description="A bandit",
            behavior="aggressive",
        )
        npc = spawn_npc(template, "test_room")

        assert get_npc_color(npc) == "RED"

    def test_merchant_color(self):
        """Test merchants are cyan."""
        template = NPCTemplate(
            id="merchant",
            name="a merchant",
            description="A merchant",
            behavior="merchant",
        )
        npc = spawn_npc(template, "test_room")

        assert get_npc_color(npc) == "CYAN"

    def test_passive_color(self):
        """Test passive NPCs are green."""
        template = NPCTemplate(
            id="deer",
            name="a deer",
            description="A deer",
            behavior="passive",
        )
        npc = spawn_npc(template, "test_room")

        assert get_npc_color(npc) == "GREEN"


class TestRoomPresenceFormatting:
    """Test NPC room presence formatting."""

    def test_single_npc(self):
        """Test single NPC uses long description."""
        template = NPCTemplate(
            id="bandit",
            name="a bandit",
            description="A bandit",
            short_description="a scrappy bandit",
            long_description="A scrappy bandit lurks here.",
        )
        npc = spawn_npc(template, "test_room")

        result = format_npc_room_presence(npc, 1)
        assert result == "A scrappy bandit lurks here."

    def test_two_npcs(self):
        """Test two NPCs shows count."""
        template = NPCTemplate(
            id="bandit",
            name="a bandit",
            description="A bandit",
            short_description="a scrappy bandit",
            long_description="A scrappy bandit is here.",
        )
        npc = spawn_npc(template, "test_room")

        result = format_npc_room_presence(npc, 2)
        # Two NPCs replace "is here" with "are here (x2)"
        assert "are here (x2)" in result

    def test_three_npcs(self):
        """Test three NPCs shows word count."""
        template = NPCTemplate(
            id="rat",
            name="a rat",
            description="A rat",
            short_description="a giant rat",
            long_description="A giant rat is here.",
        )
        npc = spawn_npc(template, "test_room")

        result = format_npc_room_presence(npc, 3)
        assert "three" in result.lower()
        assert "rats" in result.lower()


class TestBackwardCompatibility:
    """Test backward compatibility with NPCs without new fields."""

    def test_npc_without_keywords(self):
        """Test NPC without keywords still works."""
        template = NPCTemplate(
            id="old_npc",
            name="an old NPC",
            description="An old NPC",
        )
        npc = spawn_npc(template, "test_room")

        assert npc.keywords == []
        assert npc.equipment == {}
        assert npc.inventory == []

    def test_npc_without_short_description(self):
        """Test NPC without short_description uses name."""
        template = NPCTemplate(
            id="old_npc",
            name="an old NPC",
            description="An old NPC",
        )
        npc = spawn_npc(template, "test_room")

        assert npc.short_description == "an old NPC"

    def test_npc_without_long_description(self):
        """Test NPC without long_description gets default."""
        template = NPCTemplate(
            id="old_npc",
            name="an old NPC",
            description="An old NPC",
        )
        npc = spawn_npc(template, "test_room")

        assert "is here" in npc.long_description.lower()
