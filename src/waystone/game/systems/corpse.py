"""Corpse system for Waystone MUD.

Handles corpse creation, management, and decay for dead NPCs and players.
Corpses act as containers that hold the deceased's inventory and generated loot.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import structlog

from waystone.database.engine import get_session
from waystone.database.models import ItemInstance
from waystone.network import colorize

if TYPE_CHECKING:
    from waystone.game.engine import GameEngine

logger = structlog.get_logger(__name__)

# Corpse settings
CORPSE_DECAY_TIME = 300  # 5 minutes until corpse decays
NPC_CORPSE_DECAY_TIME = 300  # NPCs decay faster
PLAYER_CORPSE_DECAY_TIME = 600  # Players get more time to retrieve items


@dataclass
class CorpseInfo:
    """Information about a corpse in the world."""

    corpse_id: str  # Unique ID for this corpse
    name: str  # Display name (e.g., "corpse of a Giant Rat")
    room_id: str
    created_at: datetime
    decay_time: int  # Seconds until decay
    is_player: bool
    original_entity_id: str  # NPC ID or character UUID
    contents: list[str] = field(default_factory=list)  # List of item instance IDs


# Global corpse tracking (in-memory for quick access)
_corpses: dict[str, CorpseInfo] = {}


def get_corpse(corpse_id: str) -> CorpseInfo | None:
    """Get a corpse by ID."""
    return _corpses.get(corpse_id)


def get_corpses_in_room(room_id: str) -> list[CorpseInfo]:
    """Get all corpses in a room."""
    return [c for c in _corpses.values() if c.room_id == room_id]


def find_corpse_by_name(room_id: str, search_term: str) -> CorpseInfo | None:
    """Find a corpse in a room by name search."""
    search_lower = search_term.lower()
    for corpse in get_corpses_in_room(room_id):
        if search_lower in corpse.name.lower():
            return corpse
        # Also match just "corpse"
        if search_lower == "corpse":
            return corpse
    return None


async def create_corpse(
    name: str,
    room_id: str,
    original_entity_id: str,
    is_player: bool = False,
    loot_items: list[tuple[str, int]] | None = None,
) -> CorpseInfo:
    """
    Create a corpse in a room.

    Args:
        name: Name of the deceased (used for "corpse of {name}")
        room_id: Room where corpse appears
        original_entity_id: ID of the NPC or character
        is_player: Whether this is a player corpse
        loot_items: List of (item_template_id, quantity) to put in corpse

    Returns:
        CorpseInfo for the created corpse
    """
    corpse_id = f"corpse_{uuid4().hex[:8]}"
    decay_time = PLAYER_CORPSE_DECAY_TIME if is_player else NPC_CORPSE_DECAY_TIME

    corpse = CorpseInfo(
        corpse_id=corpse_id,
        name=f"corpse of {name}",
        room_id=room_id,
        created_at=datetime.now(),
        decay_time=decay_time,
        is_player=is_player,
        original_entity_id=original_entity_id,
        contents=[],
    )

    # Create item instances for loot and add to corpse
    if loot_items:
        async with get_session() as session:
            for template_id, quantity in loot_items:
                # Create item instance in the corpse (no room_id or owner_id yet)
                item = ItemInstance(
                    template_id=template_id,
                    quantity=quantity,
                    room_id=None,  # Not on floor
                    owner_id=None,  # Not in inventory
                    instance_properties={"in_corpse": corpse_id},
                )
                session.add(item)
                corpse.contents.append(str(item.id))

            await session.commit()

    _corpses[corpse_id] = corpse

    logger.info(
        "corpse_created",
        corpse_id=corpse_id,
        name=name,
        room_id=room_id,
        is_player=is_player,
        loot_count=len(corpse.contents),
    )

    return corpse


async def get_corpse_contents(corpse_id: str) -> list[ItemInstance]:
    """Get all items in a corpse."""
    corpse = _corpses.get(corpse_id)
    if not corpse:
        return []

    items = []
    async with get_session() as session:
        for item_id in corpse.contents:
            try:
                item = await session.get(ItemInstance, UUID(item_id))
                if item:
                    items.append(item)
            except Exception:
                continue

    return items


async def take_from_corpse(
    corpse_id: str,
    item_id: str,
    character_id: UUID,
) -> ItemInstance | None:
    """
    Take an item from a corpse and put it in a character's inventory.

    Args:
        corpse_id: ID of the corpse
        item_id: ID of the item to take
        character_id: Character taking the item

    Returns:
        The item if successful, None otherwise
    """
    corpse = _corpses.get(corpse_id)
    if not corpse or item_id not in corpse.contents:
        return None

    async with get_session() as session:
        item = await session.get(ItemInstance, UUID(item_id))
        if not item:
            return None

        # Move item to character's inventory
        item.owner_id = character_id
        item.room_id = None
        item.instance_properties = None  # Remove corpse reference

        # Remove from corpse contents
        corpse.contents.remove(item_id)

        await session.commit()

        logger.info(
            "item_taken_from_corpse",
            corpse_id=corpse_id,
            item_id=item_id,
            character_id=str(character_id),
        )

        return item


async def take_all_from_corpse(corpse_id: str, character_id: UUID) -> list[ItemInstance]:
    """
    Take all items from a corpse.

    Args:
        corpse_id: ID of the corpse
        character_id: Character taking the items

    Returns:
        List of items taken
    """
    corpse = _corpses.get(corpse_id)
    if not corpse:
        return []

    taken_items = []
    async with get_session() as session:
        for item_id in list(corpse.contents):  # Copy list since we modify it
            try:
                item = await session.get(ItemInstance, UUID(item_id))
                if item:
                    item.owner_id = character_id
                    item.room_id = None
                    item.instance_properties = None
                    taken_items.append(item)
            except Exception:
                continue

        corpse.contents.clear()
        await session.commit()

    logger.info(
        "all_items_taken_from_corpse",
        corpse_id=corpse_id,
        character_id=str(character_id),
        item_count=len(taken_items),
    )

    return taken_items


async def decay_corpse(corpse_id: str, engine: "GameEngine") -> bool:
    """
    Decay a corpse, destroying it and any remaining contents.

    Args:
        corpse_id: ID of the corpse to decay
        engine: Game engine for broadcasting

    Returns:
        True if corpse was decayed, False if not found
    """
    corpse = _corpses.get(corpse_id)
    if not corpse:
        return False

    # Delete remaining items in corpse
    async with get_session() as session:
        for item_id in corpse.contents:
            try:
                item = await session.get(ItemInstance, UUID(item_id))
                if item:
                    await session.delete(item)
            except Exception:
                continue
        await session.commit()

    # Broadcast decay message
    decay_msg = colorize(
        f"\nThe {corpse.name} crumbles to dust.",
        "MAGENTA",
    )
    engine.broadcast_to_room(corpse.room_id, decay_msg)

    # Remove from tracking
    del _corpses[corpse_id]

    logger.info(
        "corpse_decayed",
        corpse_id=corpse_id,
        name=corpse.name,
        room_id=corpse.room_id,
        items_destroyed=len(corpse.contents),
    )

    return True


async def check_corpse_decay(engine: "GameEngine") -> int:
    """
    Check for corpses ready to decay and process them.

    This should be called periodically from the game engine's tick loop.

    Args:
        engine: Game engine instance

    Returns:
        Number of corpses decayed
    """
    now = datetime.now()
    decayed_count = 0
    to_decay = []

    for corpse_id, corpse in _corpses.items():
        time_since_death = (now - corpse.created_at).total_seconds()
        if time_since_death >= corpse.decay_time:
            to_decay.append(corpse_id)

    for corpse_id in to_decay:
        if await decay_corpse(corpse_id, engine):
            decayed_count += 1

    if decayed_count > 0:
        logger.info("corpse_decay_check_completed", decayed_count=decayed_count)

    return decayed_count


def format_corpse_for_room(corpse: CorpseInfo) -> str:
    """Format a corpse for room description."""
    item_count = len(corpse.contents)
    if item_count > 0:
        return f"The {corpse.name} lies here. (contains {item_count} item{'s' if item_count != 1 else ''})"
    return f"The {corpse.name} lies here."


def format_corpse_contents(corpse: CorpseInfo, items: list[ItemInstance]) -> str:
    """Format corpse contents for display."""
    lines = [colorize(f"You look in the {corpse.name}:", "CYAN")]

    if not items:
        lines.append("  It is empty.")
    else:
        for item in items:
            qty_str = f" ({item.quantity})" if item.quantity > 1 else ""
            lines.append(f"  {item.template.name}{qty_str}")

    return "\n".join(lines)


def clear_all_corpses() -> None:
    """Clear all corpses. Useful for testing."""
    _corpses.clear()
    logger.info("all_corpses_cleared")
