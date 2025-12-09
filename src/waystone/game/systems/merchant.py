"""Merchant and shop system for Waystone MUD."""

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import structlog
import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from waystone.database.engine import get_session
from waystone.database.models import Character, ItemInstance, ItemTemplate

logger = structlog.get_logger(__name__)


@dataclass
class MerchantInventory:
    """Tracks what a merchant has for sale."""

    npc_id: str
    items: dict[str, int]  # item_template_id -> quantity (-1 = unlimited)
    gold: int  # merchant's gold for buying


# Global cache of merchant inventories loaded from YAML
_merchant_inventories: dict[str, MerchantInventory] = {}


def load_merchant_inventories() -> None:
    """Load merchant inventories from YAML configuration file."""
    global _merchant_inventories

    # Find the merchants.yaml file
    config_path = (
        Path(__file__).parent.parent.parent.parent.parent / "data" / "config" / "merchants.yaml"
    )

    if not config_path.exists():
        logger.warning("merchant_config_not_found", path=str(config_path))
        return

    try:
        with open(config_path) as f:
            data = yaml.safe_load(f)

        merchants = data.get("merchants", [])

        for merchant_data in merchants:
            npc_id = merchant_data["npc_id"]
            inventory = MerchantInventory(
                npc_id=npc_id,
                items=merchant_data.get("items", {}),
                gold=merchant_data.get("gold", 1000),
            )
            _merchant_inventories[npc_id] = inventory

        logger.info("merchant_inventories_loaded", count=len(_merchant_inventories))

    except Exception as e:
        logger.error("failed_to_load_merchant_inventories", error=str(e), exc_info=True)


async def get_merchant_inventory(npc_id: str) -> MerchantInventory | None:
    """
    Get merchant inventory for a specific NPC.

    Args:
        npc_id: The NPC ID of the merchant

    Returns:
        MerchantInventory if found, None otherwise
    """
    # Load inventories if not already loaded
    if not _merchant_inventories:
        load_merchant_inventories()

    return _merchant_inventories.get(npc_id)


def calculate_buy_price(base_value: int, character: Character) -> int:
    """
    Calculate the price the player pays to buy an item.

    Args:
        base_value: Base value of the item
        character: Character buying the item

    Returns:
        Final price the player pays
    """
    # Base price is the item's value
    # TODO: Could add charisma modifier for better prices
    return base_value


def calculate_sell_price(base_value: int, character: Character) -> int:
    """
    Calculate the price the player receives when selling an item.

    Args:
        base_value: Base value of the item
        character: Character selling the item

    Returns:
        Final price the player receives (50% of base value)
    """
    # Players get 50% of base value when selling
    # TODO: Could add charisma modifier for better prices
    return base_value // 2


async def buy_item(
    character: Character,
    merchant_npc_id: str,
    item_template_id: str,
    quantity: int = 1,
    session: AsyncSession | None = None,
) -> tuple[bool, str]:
    """
    Process a buy transaction between character and merchant.

    Args:
        character: Character buying the item
        merchant_npc_id: NPC ID of the merchant
        item_template_id: Template ID of the item to buy
        quantity: Number of items to buy (default 1)

    Returns:
        Tuple of (success, message)
    """
    # Get merchant inventory
    merchant_inventory = await get_merchant_inventory(merchant_npc_id)
    if not merchant_inventory:
        return False, "That merchant doesn't exist."

    # Check if merchant has the item
    if item_template_id not in merchant_inventory.items:
        return False, "That merchant doesn't sell that item."

    # Check merchant's stock
    stock = merchant_inventory.items[item_template_id]
    if stock != -1 and stock < quantity:
        if stock == 0:
            return False, "That item is out of stock."
        return False, f"The merchant only has {stock} of that item in stock."

    # Get item template for pricing
    async def _buy_transaction(sess: AsyncSession) -> tuple[bool, str]:
        """Inner function to handle the transaction."""
        result = await sess.execute(select(ItemTemplate).where(ItemTemplate.id == item_template_id))
        item_template = result.scalar_one_or_none()

        if not item_template:
            return False, "That item doesn't exist."

        # Calculate total price
        unit_price = calculate_buy_price(item_template.value, character)
        total_price = unit_price * quantity

        # Check if character has enough gold
        if character.gold < total_price:
            return (
                False,
                f"You don't have enough gold. You need {total_price} gold but only have {character.gold}.",
            )

        # Process transaction
        character.gold -= total_price

        # Update merchant stock if not unlimited
        if stock != -1:
            merchant_inventory.items[item_template_id] = stock - quantity

        # Create item instance(s) for the character
        if item_template.stackable:
            # Create single instance with quantity
            new_item = ItemInstance(
                template_id=item_template_id,
                owner_id=character.id,
                room_id=None,
                quantity=quantity,
            )
            sess.add(new_item)
        else:
            # Create individual instances
            for _ in range(quantity):
                new_item = ItemInstance(
                    template_id=item_template_id,
                    owner_id=character.id,
                    room_id=None,
                    quantity=1,
                )
                sess.add(new_item)

        await sess.commit()

        logger.info(
            "item_purchased",
            character_id=str(character.id),
            character_name=character.name,
            merchant_npc_id=merchant_npc_id,
            item_template_id=item_template_id,
            quantity=quantity,
            total_price=total_price,
        )

        qty_str = f"{quantity} " if quantity > 1 else ""
        return True, f"You bought {qty_str}{item_template.name} for {total_price} gold."

    # Use provided session or create a new one
    if session is not None:
        return await _buy_transaction(session)
    else:
        async with get_session() as sess:
            return await _buy_transaction(sess)


async def sell_item(
    character: Character,
    merchant_npc_id: str,
    item_id: str,
    quantity: int = 1,
    session: AsyncSession | None = None,
) -> tuple[bool, str]:
    """
    Process a sell transaction between character and merchant.

    Args:
        character: Character selling the item
        merchant_npc_id: NPC ID of the merchant
        item_id: Instance ID (UUID) of the item to sell
        quantity: Number of items to sell (default 1)

    Returns:
        Tuple of (success, message)
    """
    # Get merchant inventory
    merchant_inventory = await get_merchant_inventory(merchant_npc_id)
    if not merchant_inventory:
        return False, "That merchant doesn't exist."

    async def _sell_transaction(sess: AsyncSession) -> tuple[bool, str]:
        """Inner function to handle the transaction."""
        # Get the item instance
        # Handle both UUID string formats (with and without dashes)
        try:
            if "-" in item_id:
                item_uuid = UUID(item_id)
            else:
                # Hex format without dashes
                item_uuid = UUID(hex=item_id)
        except (ValueError, AttributeError):
            return False, "Invalid item ID format."

        result = await sess.execute(
            select(ItemInstance)
            .where(ItemInstance.id == item_uuid)
            .options(joinedload(ItemInstance.template))
        )
        item_instance = result.scalar_one_or_none()

        if not item_instance:
            return False, "That item doesn't exist."

        # Verify character owns the item
        if item_instance.owner_id != character.id:
            return False, "You don't own that item."

        # Verify item is in inventory (not in a room)
        if item_instance.room_id is not None:
            return False, "That item is not in your inventory."

        # Check if trying to sell a quest item
        if item_instance.template.quest_item:
            return False, "You cannot sell quest items."

        # Check quantity
        if item_instance.quantity < quantity:
            return False, f"You only have {item_instance.quantity} of that item."

        # Calculate price
        unit_price = calculate_sell_price(item_instance.template.value, character)
        total_price = unit_price * quantity

        # Check if merchant has enough gold
        if merchant_inventory.gold < total_price:
            return False, "The merchant doesn't have enough gold to buy that."

        # Process transaction
        character.gold += total_price
        merchant_inventory.gold -= total_price

        # Update merchant stock
        template_id = item_instance.template_id
        if template_id in merchant_inventory.items:
            if merchant_inventory.items[template_id] != -1:
                merchant_inventory.items[template_id] += quantity
        else:
            # Merchant didn't have this item before, add it
            merchant_inventory.items[template_id] = quantity

        # Remove items from character's inventory
        if item_instance.quantity == quantity:
            # Remove entire stack
            await sess.delete(item_instance)
        else:
            # Reduce quantity
            item_instance.quantity -= quantity

        await sess.commit()

        logger.info(
            "item_sold",
            character_id=str(character.id),
            character_name=character.name,
            merchant_npc_id=merchant_npc_id,
            item_id=item_id,
            quantity=quantity,
            total_price=total_price,
        )

        qty_str = f"{quantity} " if quantity > 1 else ""
        return True, f"You sold {qty_str}{item_instance.template.name} for {total_price} gold."

    # Use provided session or create a new one
    if session is not None:
        return await _sell_transaction(session)
    else:
        async with get_session() as sess:
            return await _sell_transaction(sess)


# Load merchant inventories when module is imported
load_merchant_inventories()
