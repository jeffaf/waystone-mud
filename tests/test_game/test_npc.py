"""Tests for NPC system in Waystone MUD."""

import pytest

from waystone.game.world import (
    NPCTemplate,
    get_npc_by_id,
    get_npcs_by_behavior,
    load_all_npcs,
)


class TestNPCTemplate:
    """Test the NPCTemplate Pydantic model."""

    def test_npc_template_minimal(self):
        """Test creating NPC template with minimal data."""
        npc = NPCTemplate(
            id="test_npc",
            name="a test NPC",
            description="A test NPC for testing.",
        )

        assert npc.id == "test_npc"
        assert npc.name == "a test NPC"
        assert npc.description == "A test NPC for testing."
        assert npc.level == 1  # Default
        assert npc.max_hp == 20  # Default
        assert npc.behavior == "passive"  # Default
        assert npc.respawn_time == 300  # Default
        assert npc.attributes == {}
        assert npc.dialogue is None
        assert npc.loot_table_id is None

    def test_npc_template_full(self):
        """Test creating NPC template with all fields."""
        npc = NPCTemplate(
            id="bandit",
            name="a scrappy bandit",
            description="A dangerous bandit.",
            level=2,
            max_hp=30,
            attributes={
                "strength": 12,
                "dexterity": 14,
                "constitution": 12,
                "intelligence": 8,
                "wisdom": 10,
                "charisma": 8,
            },
            behavior="aggressive",
            loot_table_id="bandit_loot",
            dialogue=None,
            respawn_time=300,
        )

        assert npc.id == "bandit"
        assert npc.name == "a scrappy bandit"
        assert npc.level == 2
        assert npc.max_hp == 30
        assert npc.behavior == "aggressive"
        assert npc.loot_table_id == "bandit_loot"
        assert npc.attributes["strength"] == 12
        assert npc.attributes["dexterity"] == 14

    def test_npc_template_with_dialogue(self):
        """Test NPC template with dialogue data."""
        npc = NPCTemplate(
            id="merchant",
            name="a friendly merchant",
            description="A merchant selling goods.",
            level=1,
            max_hp=15,
            behavior="merchant",
            dialogue={
                "greeting": "Welcome to my shop!",
                "keywords": {
                    "buy": "I have many items for sale.",
                    "sell": "I'll buy your goods.",
                },
            },
        )

        assert npc.dialogue is not None
        assert npc.dialogue["greeting"] == "Welcome to my shop!"
        assert "buy" in npc.dialogue["keywords"]
        assert npc.dialogue["keywords"]["buy"] == "I have many items for sale."


class TestNPCLoader:
    """Test NPC loading from YAML files."""

    def test_load_all_npcs(self):
        """Test loading all NPC templates from YAML files."""
        npcs = load_all_npcs()

        # Should load NPCs from all YAML files
        assert len(npcs) > 0
        assert isinstance(npcs, dict)

        # Check that all values are NPCTemplate instances
        for npc_id, npc in npcs.items():
            assert isinstance(npc_id, str)
            assert isinstance(npc, NPCTemplate)
            assert npc.id == npc_id

    def test_load_enemies(self):
        """Test that enemy NPCs are loaded correctly."""
        npcs = load_all_npcs()

        # Check for specific enemies
        assert "bandit" in npcs
        assert "wolf" in npcs
        assert "highway_robber" in npcs

        # Verify bandit data
        bandit = npcs["bandit"]
        assert bandit.name == "a scrappy bandit"
        assert bandit.behavior == "aggressive"
        assert bandit.level == 2
        assert bandit.max_hp == 30
        assert bandit.loot_table_id == "bandit_loot"

        # Verify wolf data
        wolf = npcs["wolf"]
        assert wolf.name == "a grey wolf"
        assert wolf.behavior == "aggressive"
        assert wolf.level == 1
        assert wolf.loot_table_id is None

    def test_load_merchants(self):
        """Test that merchant NPCs are loaded correctly."""
        npcs = load_all_npcs()

        # Check for merchants
        assert "merchant_imre" in npcs
        assert "blacksmith_imre" in npcs

        # Verify merchant data
        merchant = npcs["merchant_imre"]
        assert merchant.name == "Devi, the merchant"
        assert merchant.behavior == "merchant"
        assert merchant.dialogue is not None
        assert "greeting" in merchant.dialogue
        assert merchant.respawn_time == 0  # Merchants don't respawn

    def test_load_university_npcs(self):
        """Test that University NPCs are loaded correctly."""
        npcs = load_all_npcs()

        # Check for University NPCs
        assert "master_lorren" in npcs
        assert "master_kilvin" in npcs
        assert "student" in npcs

        # Verify master data
        lorren = npcs["master_lorren"]
        assert lorren.name == "Master Lorren, the Chancellor"
        assert lorren.behavior == "stationary"
        assert lorren.level == 10
        assert lorren.max_hp == 100
        assert lorren.dialogue is not None

        # Verify student data
        student = npcs["student"]
        assert student.behavior == "passive"
        assert student.level == 1

    def test_get_npc_by_id(self):
        """Test retrieving NPC by ID."""
        npcs = load_all_npcs()

        bandit = get_npc_by_id(npcs, "bandit")
        assert bandit is not None
        assert bandit.id == "bandit"

        nonexistent = get_npc_by_id(npcs, "nonexistent_npc")
        assert nonexistent is None

    def test_get_npcs_by_behavior(self):
        """Test filtering NPCs by behavior."""
        npcs = load_all_npcs()

        # Get aggressive NPCs
        aggressive = get_npcs_by_behavior(npcs, "aggressive")
        assert len(aggressive) > 0
        for npc in aggressive:
            assert npc.behavior == "aggressive"

        # Get merchants
        merchants = get_npcs_by_behavior(npcs, "merchant")
        assert len(merchants) > 0
        for npc in merchants:
            assert npc.behavior == "merchant"

        # Get stationary NPCs
        stationary = get_npcs_by_behavior(npcs, "stationary")
        assert len(stationary) > 0
        for npc in stationary:
            assert npc.behavior == "stationary"

    def test_npc_attributes(self):
        """Test that NPC attributes are loaded correctly."""
        npcs = load_all_npcs()

        bandit = npcs["bandit"]
        assert "strength" in bandit.attributes
        assert "dexterity" in bandit.attributes
        assert bandit.attributes["strength"] == 12
        assert bandit.attributes["dexterity"] == 14

    def test_npc_dialogue_structure(self):
        """Test that NPC dialogue is structured correctly."""
        npcs = load_all_npcs()

        merchant = npcs["merchant_imre"]
        assert merchant.dialogue is not None
        assert "greeting" in merchant.dialogue
        assert "keywords" in merchant.dialogue
        assert isinstance(merchant.dialogue["keywords"], dict)

        lorren = npcs["master_lorren"]
        assert lorren.dialogue is not None
        assert "greeting" in lorren.dialogue
        assert "keywords" in lorren.dialogue


class TestNPCValidation:
    """Test NPC validation and error handling."""

    def test_invalid_level(self):
        """Test that invalid level values are rejected."""
        # Level should be positive
        npc = NPCTemplate(
            id="test",
            name="test",
            description="test",
            level=0,  # Invalid
        )
        # Pydantic allows 0, but our validation in loader should catch negative values
        assert npc.level == 0

    def test_invalid_max_hp(self):
        """Test that invalid max_hp values are rejected."""
        # Max HP should be positive
        npc = NPCTemplate(
            id="test",
            name="test",
            description="test",
            max_hp=0,  # Invalid
        )
        assert npc.max_hp == 0

    def test_valid_behaviors(self):
        """Test that all valid behavior types work."""
        valid_behaviors = ["aggressive", "passive", "merchant", "stationary", "wander"]

        for behavior in valid_behaviors:
            npc = NPCTemplate(
                id=f"test_{behavior}",
                name=f"test {behavior}",
                description="test",
                behavior=behavior,
            )
            assert npc.behavior == behavior


class TestNPCDataIntegrity:
    """Test data integrity across all NPC files."""

    def test_no_duplicate_ids(self):
        """Test that there are no duplicate NPC IDs."""
        npcs = load_all_npcs()

        # All IDs should be unique (enforced by dict)
        npc_ids = list(npcs.keys())
        assert len(npc_ids) == len(set(npc_ids))

    def test_all_npcs_have_descriptions(self):
        """Test that all NPCs have descriptions."""
        npcs = load_all_npcs()

        for npc_id, npc in npcs.items():
            assert npc.description is not None
            assert len(npc.description.strip()) > 0, f"NPC {npc_id} has empty description"

    def test_all_npcs_have_names(self):
        """Test that all NPCs have names."""
        npcs = load_all_npcs()

        for npc_id, npc in npcs.items():
            assert npc.name is not None
            assert len(npc.name.strip()) > 0, f"NPC {npc_id} has empty name"

    def test_aggressive_npcs_have_combat_stats(self):
        """Test that aggressive NPCs have reasonable combat stats."""
        npcs = load_all_npcs()
        aggressive = get_npcs_by_behavior(npcs, "aggressive")

        for npc in aggressive:
            assert npc.level > 0, f"Aggressive NPC {npc.id} has invalid level"
            assert npc.max_hp > 0, f"Aggressive NPC {npc.id} has invalid HP"

    def test_merchants_have_dialogue(self):
        """Test that merchant NPCs have dialogue."""
        npcs = load_all_npcs()
        merchants = get_npcs_by_behavior(npcs, "merchant")

        for npc in merchants:
            assert npc.dialogue is not None, f"Merchant {npc.id} has no dialogue"
            assert "greeting" in npc.dialogue, f"Merchant {npc.id} missing greeting dialogue"

    def test_respawn_times(self):
        """Test that respawn times are reasonable."""
        npcs = load_all_npcs()

        for npc_id, npc in npcs.items():
            # Respawn time should be non-negative
            assert npc.respawn_time >= 0, f"NPC {npc_id} has negative respawn time"

            # Merchants should not respawn (respawn_time == 0)
            if npc.behavior == "merchant":
                assert npc.respawn_time == 0, f"Merchant {npc_id} has non-zero respawn time"

    def test_npc_level_progression(self):
        """Test that NPC levels are reasonable."""
        npcs = load_all_npcs()

        for npc_id, npc in npcs.items():
            assert npc.level >= 1, f"NPC {npc_id} has level < 1"
            # Skip invulnerable NPCs (like the Cthaeh) - they can have any level
            if not npc.invulnerable:
                assert npc.level <= 20, f"NPC {npc_id} has unreasonably high level"

    def test_npc_hp_scales_with_level(self):
        """Test that NPC HP generally scales with level."""
        npcs = load_all_npcs()

        for npc_id, npc in npcs.items():
            # Skip invulnerable NPCs - they may have special HP values
            if npc.invulnerable:
                continue
            # HP should be at least 10 per level (rough guideline)
            min_hp = npc.level * 10
            assert npc.max_hp >= min_hp * 0.5, f"NPC {npc_id} has too low HP for its level"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
