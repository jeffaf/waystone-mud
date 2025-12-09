"""Loot generation system for Waystone MUD."""

import random
from dataclasses import dataclass, field
from pathlib import Path

import structlog
import yaml

from waystone.config import get_settings
from waystone.database.engine import get_session
from waystone.database.models import ItemInstance

logger = structlog.get_logger(__name__)


@dataclass
class LootEntry:
    """
    Represents a single item in a loot table.

    Attributes:
        item_id: Template ID of the item to drop
        chance: Probability of dropping (0.0-1.0)
        min_quantity: Minimum number of items to drop
        max_quantity: Maximum number of items to drop
    """

    item_id: str
    chance: float
    min_quantity: int = 1
    max_quantity: int = 1

    def __post_init__(self) -> None:
        """Validate loot entry parameters."""
        if not 0.0 <= self.chance <= 1.0:
            raise ValueError(f"Chance must be between 0.0 and 1.0, got {self.chance}")
        if self.min_quantity < 0:
            raise ValueError(f"min_quantity must be >= 0, got {self.min_quantity}")
        if self.max_quantity < self.min_quantity:
            raise ValueError(
                f"max_quantity ({self.max_quantity}) must be >= min_quantity ({self.min_quantity})"
            )


@dataclass
class LootTable:
    """
    Defines a complete loot table for an NPC or container.

    Attributes:
        id: Unique identifier for this loot table
        entries: List of possible item drops
        gold_min: Minimum gold to drop
        gold_max: Maximum gold to drop
    """

    id: str
    entries: list[LootEntry] = field(default_factory=list)
    gold_min: int = 0
    gold_max: int = 0

    def __post_init__(self) -> None:
        """Validate loot table parameters."""
        if self.gold_min < 0:
            raise ValueError(f"gold_min must be >= 0, got {self.gold_min}")
        if self.gold_max < self.gold_min:
            raise ValueError(f"gold_max ({self.gold_max}) must be >= gold_min ({self.gold_min})")


# Global loot table cache
_loot_tables: dict[str, LootTable] = {}
_tables_loaded = False


def load_loot_tables(config_path: Path | None = None) -> dict[str, LootTable]:
    """
    Load loot tables from YAML configuration file.

    Args:
        config_path: Optional path to loot_tables.yaml. If None, uses default location.

    Returns:
        Dictionary mapping table IDs to LootTable objects

    Raises:
        FileNotFoundError: If loot_tables.yaml doesn't exist
        ValueError: If YAML is malformed or contains invalid data
    """
    global _loot_tables, _tables_loaded

    if config_path is None:
        settings = get_settings()
        config_path = settings.config_dir / "loot_tables.yaml"

    if not config_path.exists():
        logger.warning(
            "loot_tables_file_not_found",
            path=str(config_path),
        )
        _loot_tables = {}
        _tables_loaded = True
        return _loot_tables

    try:
        with open(config_path) as f:
            data = yaml.safe_load(f)

        if not data or "loot_tables" not in data:
            logger.warning(
                "loot_tables_missing_key",
                path=str(config_path),
            )
            _loot_tables = {}
            _tables_loaded = True
            return _loot_tables

        tables: dict[str, LootTable] = {}

        for table_data in data["loot_tables"]:
            table_id = table_data["id"]

            # Parse entries
            entries = []
            for entry_data in table_data.get("entries", []):
                entry = LootEntry(
                    item_id=entry_data["item_id"],
                    chance=entry_data["chance"],
                    min_quantity=entry_data.get("min_quantity", 1),
                    max_quantity=entry_data.get("max_quantity", 1),
                )
                entries.append(entry)

            # Create loot table
            table = LootTable(
                id=table_id,
                entries=entries,
                gold_min=table_data.get("gold_min", 0),
                gold_max=table_data.get("gold_max", 0),
            )

            tables[table_id] = table

            logger.debug(
                "loot_table_loaded",
                table_id=table_id,
                entry_count=len(entries),
                gold_range=f"{table.gold_min}-{table.gold_max}",
            )

        _loot_tables = tables
        _tables_loaded = True

        logger.info(
            "loot_tables_loaded",
            path=str(config_path),
            table_count=len(tables),
        )

        return tables

    except Exception as e:
        logger.error(
            "loot_tables_load_failed",
            path=str(config_path),
            error=str(e),
            exc_info=True,
        )
        raise


def get_loot_table(table_id: str) -> LootTable | None:
    """
    Get a loot table by ID.

    Args:
        table_id: The loot table identifier

    Returns:
        LootTable if found, None otherwise
    """
    global _loot_tables, _tables_loaded

    if not _tables_loaded:
        load_loot_tables()

    return _loot_tables.get(table_id)


async def generate_loot(table_id: str) -> list[tuple[str, int]]:
    """
    Generate loot items from a loot table.

    This function rolls for each item in the loot table based on its drop chance.
    Items that successfully roll are added to the result with a random quantity
    between their min and max values.

    Args:
        table_id: ID of the loot table to use

    Returns:
        List of tuples containing (item_template_id, quantity)
        Returns empty list if table not found

    Example:
        >>> loot = await generate_loot("bandit_loot")
        >>> # Returns something like: [("dagger", 1), ("bread", 2), ("gold", 15)]
    """
    table = get_loot_table(table_id)

    if not table:
        logger.warning(
            "loot_table_not_found",
            table_id=table_id,
        )
        return []

    loot_items: list[tuple[str, int]] = []

    # Roll for each entry in the table
    for entry in table.entries:
        roll = random.random()

        if roll <= entry.chance:
            # Item drops! Determine quantity
            quantity = random.randint(entry.min_quantity, entry.max_quantity)

            if quantity > 0:
                loot_items.append((entry.item_id, quantity))

                logger.debug(
                    "loot_item_rolled",
                    table_id=table_id,
                    item_id=entry.item_id,
                    quantity=quantity,
                    roll=roll,
                    chance=entry.chance,
                )

    # Roll for gold if applicable
    if table.gold_max > 0:
        gold_amount = random.randint(table.gold_min, table.gold_max)
        if gold_amount > 0:
            loot_items.append(("gold", gold_amount))

            logger.debug(
                "loot_gold_rolled",
                table_id=table_id,
                gold=gold_amount,
            )

    logger.info(
        "loot_generated",
        table_id=table_id,
        item_count=len(loot_items),
        items=loot_items,
    )

    return loot_items


async def drop_loot_to_room(
    room_id: str,
    loot: list[tuple[str, int]],
) -> list[ItemInstance]:
    """
    Create item instances in a room from generated loot.

    This function takes the results from generate_loot() and creates actual
    ItemInstance objects in the database, placing them in the specified room.

    Args:
        room_id: ID of the room where loot should be placed
        loot: List of (item_template_id, quantity) tuples from generate_loot()

    Returns:
        List of created ItemInstance objects

    Note:
        Gold is handled as a special case - "gold" template_id represents currency
        and may need special handling in your game (e.g., direct currency add vs item).
    """
    created_instances: list[ItemInstance] = []

    async with get_session() as session:
        for item_id, quantity in loot:
            # Skip gold for now - this would need currency system integration
            if item_id == "gold":
                logger.debug(
                    "loot_gold_dropped",
                    room_id=room_id,
                    amount=quantity,
                )
                continue

            # Create item instance
            instance = ItemInstance(
                template_id=item_id,
                room_id=room_id,
                quantity=quantity,
            )

            session.add(instance)
            created_instances.append(instance)

            logger.debug(
                "loot_item_created",
                room_id=room_id,
                template_id=item_id,
                quantity=quantity,
                instance_id=str(instance.id),
            )

        await session.commit()

        logger.info(
            "loot_dropped_to_room",
            room_id=room_id,
            item_count=len(created_instances),
        )

    return created_instances
