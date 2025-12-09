"""Tests for the loot generation system."""

import tempfile
from pathlib import Path

import pytest
import yaml

from waystone.game.systems.loot import (
    LootEntry,
    LootTable,
    drop_loot_to_room,
    generate_loot,
    get_loot_table,
    load_loot_tables,
)


class TestLootEntry:
    """Test LootEntry dataclass validation."""

    def test_valid_loot_entry(self):
        """Test creating a valid loot entry."""
        entry = LootEntry(item_id="sword", chance=0.5, min_quantity=1, max_quantity=3)

        assert entry.item_id == "sword"
        assert entry.chance == 0.5
        assert entry.min_quantity == 1
        assert entry.max_quantity == 3

    def test_loot_entry_defaults(self):
        """Test default values for optional parameters."""
        entry = LootEntry(item_id="potion", chance=0.3)

        assert entry.min_quantity == 1
        assert entry.max_quantity == 1

    def test_invalid_chance_too_high(self):
        """Test that chance > 1.0 raises ValueError."""
        with pytest.raises(ValueError, match="Chance must be between 0.0 and 1.0"):
            LootEntry(item_id="sword", chance=1.5)

    def test_invalid_chance_negative(self):
        """Test that negative chance raises ValueError."""
        with pytest.raises(ValueError, match="Chance must be between 0.0 and 1.0"):
            LootEntry(item_id="sword", chance=-0.1)

    def test_invalid_min_quantity_negative(self):
        """Test that negative min_quantity raises ValueError."""
        with pytest.raises(ValueError, match="min_quantity must be >= 0"):
            LootEntry(item_id="sword", chance=0.5, min_quantity=-1)

    def test_invalid_max_less_than_min(self):
        """Test that max_quantity < min_quantity raises ValueError."""
        with pytest.raises(ValueError, match="max_quantity.*must be >= min_quantity"):
            LootEntry(item_id="sword", chance=0.5, min_quantity=5, max_quantity=3)


class TestLootTable:
    """Test LootTable dataclass validation."""

    def test_valid_loot_table(self):
        """Test creating a valid loot table."""
        entries = [
            LootEntry(item_id="sword", chance=0.3),
            LootEntry(item_id="potion", chance=0.5),
        ]
        table = LootTable(id="bandit", entries=entries, gold_min=10, gold_max=50)

        assert table.id == "bandit"
        assert len(table.entries) == 2
        assert table.gold_min == 10
        assert table.gold_max == 50

    def test_loot_table_defaults(self):
        """Test default values for optional parameters."""
        table = LootTable(id="wolf")

        assert table.entries == []
        assert table.gold_min == 0
        assert table.gold_max == 0

    def test_invalid_gold_min_negative(self):
        """Test that negative gold_min raises ValueError."""
        with pytest.raises(ValueError, match="gold_min must be >= 0"):
            LootTable(id="bandit", gold_min=-5)

    def test_invalid_gold_max_less_than_min(self):
        """Test that gold_max < gold_min raises ValueError."""
        with pytest.raises(ValueError, match="gold_max.*must be >= gold_min"):
            LootTable(id="bandit", gold_min=50, gold_max=10)


class TestLoadLootTables:
    """Test loading loot tables from YAML configuration."""

    def test_load_valid_yaml(self):
        """Test loading a valid loot tables YAML file."""
        # Create temporary YAML file
        yaml_content = {
            "loot_tables": [
                {
                    "id": "test_bandit",
                    "gold_min": 5,
                    "gold_max": 20,
                    "entries": [
                        {"item_id": "dagger", "chance": 0.3},
                        {"item_id": "bread", "chance": 0.5, "min_quantity": 1, "max_quantity": 2},
                    ],
                },
                {
                    "id": "test_wolf",
                    "entries": [
                        {"item_id": "wolf_pelt", "chance": 0.8},
                    ],
                },
            ]
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(yaml_content, f)
            temp_path = Path(f.name)

        try:
            tables = load_loot_tables(temp_path)

            assert "test_bandit" in tables
            assert "test_wolf" in tables

            # Verify bandit table
            bandit = tables["test_bandit"]
            assert bandit.id == "test_bandit"
            assert bandit.gold_min == 5
            assert bandit.gold_max == 20
            assert len(bandit.entries) == 2

            # Verify wolf table
            wolf = tables["test_wolf"]
            assert wolf.id == "test_wolf"
            assert wolf.gold_min == 0
            assert wolf.gold_max == 0
            assert len(wolf.entries) == 1

        finally:
            temp_path.unlink()

    def test_load_missing_file(self):
        """Test loading from non-existent file returns empty dict."""
        tables = load_loot_tables(Path("/nonexistent/path.yaml"))
        assert tables == {}

    def test_load_empty_yaml(self):
        """Test loading empty YAML file returns empty dict."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")
            temp_path = Path(f.name)

        try:
            tables = load_loot_tables(temp_path)
            assert tables == {}
        finally:
            temp_path.unlink()

    def test_load_yaml_missing_loot_tables_key(self):
        """Test loading YAML without 'loot_tables' key returns empty dict."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"other_data": []}, f)
            temp_path = Path(f.name)

        try:
            tables = load_loot_tables(temp_path)
            assert tables == {}
        finally:
            temp_path.unlink()


class TestGetLootTable:
    """Test retrieving loot tables."""

    def test_get_existing_table(self):
        """Test getting a table that exists."""
        # Create temporary YAML file with test data
        yaml_content = {
            "loot_tables": [
                {
                    "id": "test_table",
                    "entries": [{"item_id": "item1", "chance": 0.5}],
                },
            ]
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(yaml_content, f)
            temp_path = Path(f.name)

        try:
            load_loot_tables(temp_path)
            table = get_loot_table("test_table")

            assert table is not None
            assert table.id == "test_table"
        finally:
            temp_path.unlink()

    def test_get_nonexistent_table(self):
        """Test getting a table that doesn't exist returns None."""
        table = get_loot_table("nonexistent_table")
        assert table is None


class TestGenerateLoot:
    """Test loot generation logic."""

    @pytest.mark.asyncio
    async def test_generate_loot_nonexistent_table(self):
        """Test generating loot from non-existent table returns empty list."""
        loot = await generate_loot("nonexistent_table")
        assert loot == []

    @pytest.mark.asyncio
    async def test_generate_loot_deterministic_100_percent(self):
        """Test loot generation with 100% chance always drops."""
        # Create table with guaranteed drops
        yaml_content = {
            "loot_tables": [
                {
                    "id": "guaranteed_loot",
                    "entries": [
                        {"item_id": "sword", "chance": 1.0, "min_quantity": 2, "max_quantity": 2},
                    ],
                },
            ]
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(yaml_content, f)
            temp_path = Path(f.name)

        try:
            load_loot_tables(temp_path)
            loot = await generate_loot("guaranteed_loot")

            # Should always get sword with quantity 2
            assert len(loot) == 1
            assert loot[0] == ("sword", 2)
        finally:
            temp_path.unlink()

    @pytest.mark.asyncio
    async def test_generate_loot_with_gold(self):
        """Test loot generation includes gold."""
        yaml_content = {
            "loot_tables": [
                {
                    "id": "gold_loot",
                    "gold_min": 10,
                    "gold_max": 10,
                    "entries": [],
                },
            ]
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(yaml_content, f)
            temp_path = Path(f.name)

        try:
            load_loot_tables(temp_path)
            loot = await generate_loot("gold_loot")

            # Should get exactly 10 gold
            assert ("gold", 10) in loot
        finally:
            temp_path.unlink()

    @pytest.mark.asyncio
    async def test_generate_loot_zero_percent_chance(self):
        """Test loot with 0% chance never drops."""
        yaml_content = {
            "loot_tables": [
                {
                    "id": "impossible_loot",
                    "entries": [
                        {"item_id": "rare_item", "chance": 0.0},
                    ],
                },
            ]
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(yaml_content, f)
            temp_path = Path(f.name)

        try:
            load_loot_tables(temp_path)

            # Generate multiple times to ensure 0% is respected
            for _ in range(10):
                loot = await generate_loot("impossible_loot")
                assert loot == []
        finally:
            temp_path.unlink()


class TestDropLootToRoom:
    """Test dropping loot items into rooms."""

    @pytest.mark.asyncio
    async def test_drop_loot_to_room_empty_list(self):
        """Test dropping empty loot list creates no items."""
        instances = await drop_loot_to_room("test_room", [])
        assert instances == []

    @pytest.mark.asyncio
    async def test_drop_loot_skips_gold(self):
        """Test that gold is skipped (not a physical item)."""
        loot = [("gold", 50)]
        instances = await drop_loot_to_room("test_room", loot)

        # Gold should not create item instances
        assert instances == []

    # Note: Testing actual item creation requires database setup
    # which is covered by integration tests
