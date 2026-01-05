"""
Item loader module for Waystone MUD.

Handles loading item templates from YAML files and populating the database.
"""

from pathlib import Path
from typing import Any

import structlog
import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waystone.database.models import ItemSlot, ItemTemplate, ItemType

logger = structlog.get_logger(__name__)


class ItemLoadError(Exception):
    """Raised when there's an error loading item data."""

    pass


class ItemValidationError(Exception):
    """Raised when item validation fails."""

    pass


# Mapping from YAML type strings to ItemType enum
ITEM_TYPE_MAP = {
    "weapon": ItemType.WEAPON,
    "armor": ItemType.ARMOR,
    "consumable": ItemType.CONSUMABLE,
    "quest": ItemType.QUEST,
    "misc": ItemType.MISC,
    "container": ItemType.CONTAINER,
}

# Mapping from YAML slot strings to ItemSlot enum
ITEM_SLOT_MAP = {
    "head": ItemSlot.HEAD,
    "body": ItemSlot.BODY,
    "hands": ItemSlot.HANDS,
    "legs": ItemSlot.LEGS,
    "feet": ItemSlot.FEET,
    "main_hand": ItemSlot.MAIN_HAND,
    "off_hand": ItemSlot.OFF_HAND,
    "accessory": ItemSlot.ACCESSORY,
    "none": ItemSlot.NONE,
}


def load_yaml_file(file_path: Path) -> list[dict[str, Any]]:
    """
    Load a YAML file containing item definitions.

    Args:
        file_path: Path to the YAML file

    Returns:
        List of item dictionaries

    Raises:
        ItemLoadError: If the file cannot be loaded or parsed
    """
    try:
        with open(file_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data:
            raise ItemLoadError(f"Empty YAML file: {file_path}")

        if "items" not in data:
            raise ItemLoadError(f"Missing 'items' key in {file_path}")

        items = data["items"]
        if not isinstance(items, list):
            raise ItemLoadError(f"'items' must be a list in {file_path}")

        return items

    except yaml.YAMLError as e:
        raise ItemLoadError(f"YAML parsing error in {file_path}: {e}")
    except FileNotFoundError:
        raise ItemLoadError(f"File not found: {file_path}")
    except Exception as e:
        raise ItemLoadError(f"Error loading {file_path}: {e}")


def validate_item_data(item_data: dict[str, Any], file_path: Path) -> None:
    """
    Validate that an item dictionary has all required fields.

    Args:
        item_data: Dictionary containing item data
        file_path: Path to the source file (for error messages)

    Raises:
        ItemValidationError: If required fields are missing or invalid
    """
    required_fields = ["id", "name", "description", "type"]

    for field in required_fields:
        if field not in item_data:
            item_id = item_data.get("id", "unknown")
            raise ItemValidationError(
                f"Item '{item_id}' in {file_path} missing required field: {field}"
            )

    # Validate item type
    item_type = item_data.get("type", "").lower()
    if item_type not in ITEM_TYPE_MAP:
        raise ItemValidationError(
            f"Item '{item_data['id']}' in {file_path} has invalid type '{item_type}' "
            f"(must be one of: {', '.join(ITEM_TYPE_MAP.keys())})"
        )

    # Validate slot if present
    slot = item_data.get("slot", "none").lower()
    if slot not in ITEM_SLOT_MAP:
        raise ItemValidationError(
            f"Item '{item_data['id']}' in {file_path} has invalid slot '{slot}' "
            f"(must be one of: {', '.join(ITEM_SLOT_MAP.keys())})"
        )

    # Validate numeric fields
    if "weight" in item_data and not isinstance(item_data["weight"], (int, float)):
        raise ItemValidationError(
            f"Item '{item_data['id']}' in {file_path} has invalid weight (must be a number)"
        )

    if "value" in item_data and not isinstance(item_data["value"], int):
        raise ItemValidationError(
            f"Item '{item_data['id']}' in {file_path} has invalid value (must be an integer)"
        )

    # Validate boolean fields
    for bool_field in ["stackable", "unique", "quest_item"]:
        if bool_field in item_data and not isinstance(item_data[bool_field], bool):
            raise ItemValidationError(
                f"Item '{item_data['id']}' in {file_path} has invalid {bool_field} (must be boolean)"
            )


def create_item_template_from_data(item_data: dict[str, Any]) -> ItemTemplate:
    """
    Create an ItemTemplate instance from dictionary data.

    Args:
        item_data: Dictionary containing item data

    Returns:
        ItemTemplate instance

    Raises:
        ItemValidationError: If creation fails
    """
    try:
        return ItemTemplate(
            id=item_data["id"],
            name=item_data["name"],
            description=item_data["description"],
            item_type=ITEM_TYPE_MAP[item_data["type"].lower()],
            slot=ITEM_SLOT_MAP.get(item_data.get("slot", "none").lower(), ItemSlot.NONE),
            weight=float(item_data.get("weight", 0.0)),
            value=int(item_data.get("value", 0)),
            stackable=bool(item_data.get("stackable", False)),
            unique=bool(item_data.get("unique", False)),
            quest_item=bool(item_data.get("quest_item", False)),
            properties=item_data.get("properties"),
        )
    except Exception as e:
        raise ItemValidationError(
            f"Failed to create item template '{item_data.get('id', 'unknown')}': {e}"
        )


def load_items_from_directory(directory: Path) -> list[ItemTemplate]:
    """
    Load all item YAML files from a directory.

    Args:
        directory: Path to the directory containing YAML files

    Returns:
        List of ItemTemplate instances

    Raises:
        ItemLoadError: If directory doesn't exist or files can't be loaded
        ItemValidationError: If item validation fails
    """
    if not directory.exists():
        logger.warning("item_directory_not_found", directory=str(directory))
        return []

    if not directory.is_dir():
        raise ItemLoadError(f"Not a directory: {directory}")

    items: list[ItemTemplate] = []
    seen_ids: set[str] = set()

    yaml_files = list(directory.glob("*.yaml")) + list(directory.glob("*.yml"))

    if not yaml_files:
        logger.warning("no_item_yaml_files_found", directory=str(directory))
        return []

    for yaml_file in yaml_files:
        try:
            item_list = load_yaml_file(yaml_file)

            for item_data in item_list:
                validate_item_data(item_data, yaml_file)
                item = create_item_template_from_data(item_data)

                # Check for duplicate item IDs
                if item.id in seen_ids:
                    logger.warning(
                        "duplicate_item_id",
                        item_id=item.id,
                        file=str(yaml_file),
                    )
                    continue

                seen_ids.add(item.id)
                items.append(item)

        except ItemLoadError as e:
            logger.warning("item_file_load_error", file=str(yaml_file), error=str(e))
            continue

    return items


async def populate_item_templates(session: AsyncSession, data_dir: Path | None = None) -> int:
    """
    Load item templates from YAML files and populate the database.

    This function performs an upsert - it will add new items and update
    existing ones based on their ID.

    Args:
        session: Database session
        data_dir: Path to the items directory. If None, uses default location.

    Returns:
        Number of items loaded/updated

    Raises:
        ItemLoadError: If loading fails
        ItemValidationError: If validation fails
    """
    if data_dir is None:
        # Default to data/world/items/ relative to project root
        data_dir = Path(__file__).parent.parent.parent.parent.parent / "data" / "world" / "items"

    # Also check for items.yaml in the world directory
    world_dir = data_dir.parent
    items_yaml = world_dir / "items.yaml"

    all_items: list[ItemTemplate] = []

    # Load from items directory if it exists
    if data_dir.exists():
        all_items.extend(load_items_from_directory(data_dir))

    # Load from items.yaml in world directory
    if items_yaml.exists():
        try:
            item_list = load_yaml_file(items_yaml)
            seen_ids = {item.id for item in all_items}

            for item_data in item_list:
                if item_data.get("id") in seen_ids:
                    continue  # Skip duplicates
                validate_item_data(item_data, items_yaml)
                item = create_item_template_from_data(item_data)
                all_items.append(item)

        except ItemLoadError as e:
            logger.warning("items_yaml_load_error", error=str(e))

    if not all_items:
        logger.warning("no_item_templates_loaded")
        return 0

    # Get existing item IDs in database
    result = await session.execute(select(ItemTemplate.id))
    existing_ids = {row[0] for row in result.all()}

    added = 0
    updated = 0

    for item in all_items:
        if item.id in existing_ids:
            # Update existing item
            await session.merge(item)
            updated += 1
        else:
            # Add new item
            session.add(item)
            added += 1

    await session.commit()

    logger.info(
        "item_templates_populated",
        added=added,
        updated=updated,
        total=len(all_items),
    )

    return len(all_items)


async def load_all_items(session: AsyncSession, data_dir: Path | None = None) -> int:
    """
    Load all item templates from YAML and populate the database.

    This is the main entry point for loading item templates.

    Args:
        session: Database session
        data_dir: Path to the items directory. If None, uses default location.

    Returns:
        Number of items loaded

    Raises:
        ItemLoadError: If loading fails
        ItemValidationError: If validation fails
    """
    count = await populate_item_templates(session, data_dir)
    print(f"✅ Successfully loaded {count} item templates")
    return count
