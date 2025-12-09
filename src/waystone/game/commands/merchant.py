"""Merchant and shop commands for Waystone MUD."""

from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from waystone.database.engine import get_session
from waystone.database.models import Character, ItemInstance, ItemTemplate
from waystone.game.systems import merchant as merchant_system
from waystone.network import colorize

from .base import Command, CommandContext

logger = structlog.get_logger(__name__)


class ListCommand(Command):
    """List items available in a merchant's shop."""

    name = "list"
    aliases = ["shop"]
    help_text = "list - Show merchant's inventory and prices"
    min_args = 0

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the list command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        try:
            async with get_session() as session:
                # Get character
                result = await session.execute(
                    select(Character).where(Character.id == UUID(ctx.session.character_id))
                )
                character = result.scalar_one_or_none()

                if not character:
                    await ctx.connection.send_line(colorize("Character not found.", "RED"))
                    return

                # For now, check if there's a merchant in the room by room ID
                # This is a simplified implementation - a full NPC system would be better
                merchant_npc_id = self._get_merchant_in_room(character.current_room_id)

                if not merchant_npc_id:
                    await ctx.connection.send_line(colorize("There is no merchant here.", "YELLOW"))
                    return

                # Get merchant inventory
                merchant_inventory = await merchant_system.get_merchant_inventory(merchant_npc_id)

                if not merchant_inventory:
                    await ctx.connection.send_line(
                        colorize("This merchant has nothing to sell.", "YELLOW")
                    )
                    return

                # Display header
                await ctx.connection.send_line("")
                await ctx.connection.send_line(colorize("=== Merchant's Wares ===", "CYAN"))
                await ctx.connection.send_line("")

                # Get all item templates for this merchant
                item_ids = list(merchant_inventory.items.keys())

                if not item_ids:
                    await ctx.connection.send_line(
                        colorize("The merchant has nothing for sale.", "DIM")
                    )
                    return

                template_result = await session.execute(
                    select(ItemTemplate).where(ItemTemplate.id.in_(item_ids))
                )
                templates = template_result.scalars().all()

                # Create a mapping for quick lookup
                template_map: dict[str, ItemTemplate] = {t.id: t for t in templates}

                # Display items
                for item_id, stock in sorted(merchant_inventory.items.items()):
                    template = template_map.get(item_id)
                    if not template:
                        continue

                    price = merchant_system.calculate_buy_price(template.value, character)
                    stock_str = "unlimited" if stock == -1 else f"{stock} in stock"

                    await ctx.connection.send_line(
                        f"  {colorize(template.name, 'WHITE'):40} "
                        f"{colorize(f'{price:4} gold', 'YELLOW'):15} "
                        f"{colorize(f'({stock_str})', 'DIM')}"
                    )

                # Show player's gold
                await ctx.connection.send_line("")
                await ctx.connection.send_line(
                    f"You have {colorize(f'{character.gold} gold', 'GREEN')}"
                )

                logger.debug(
                    "merchant_list_viewed",
                    character_id=ctx.session.character_id,
                    merchant_npc_id=merchant_npc_id,
                )

        except Exception as e:
            logger.error("list_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Failed to list merchant items. Please try again.", "RED")
            )

    def _get_merchant_in_room(self, room_id: str) -> str | None:
        """
        Determine if there's a merchant in the current room.

        This is a simplified implementation based on room IDs.
        A full NPC system would track NPCs in rooms dynamically.
        """
        # Map room IDs to merchant NPC IDs
        room_to_merchant = {
            "imre_devi_shop": "merchant_imre",
            "imre_blacksmith": "blacksmith_imre",
            "imre_apothecary": "apothecary_imre",
            "university_bookshop": "bookshop_university",
            "imre_inn_waystone": "tavern_keeper",
        }

        return room_to_merchant.get(room_id)


class BuyCommand(Command):
    """Purchase an item from a merchant."""

    name = "buy"
    aliases = []
    help_text = "buy <item> [quantity] - Purchase an item from the merchant"
    min_args = 1

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the buy command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        # Parse arguments
        quantity = 1
        item_name_parts = ctx.args

        # Check if last argument is a number
        if len(ctx.args) > 1 and ctx.args[-1].isdigit():
            quantity = int(ctx.args[-1])
            item_name_parts = ctx.args[:-1]

        item_name = " ".join(item_name_parts).lower()

        if quantity < 1:
            await ctx.connection.send_line(colorize("Quantity must be at least 1.", "YELLOW"))
            return

        try:
            async with get_session() as session:
                # Get character
                result = await session.execute(
                    select(Character).where(Character.id == UUID(ctx.session.character_id))
                )
                character = result.scalar_one_or_none()

                if not character:
                    await ctx.connection.send_line(colorize("Character not found.", "RED"))
                    return

                # Find merchant in room
                merchant_npc_id = self._get_merchant_in_room(character.current_room_id)

                if not merchant_npc_id:
                    await ctx.connection.send_line(colorize("There is no merchant here.", "YELLOW"))
                    return

                # Get merchant inventory
                merchant_inventory = await merchant_system.get_merchant_inventory(merchant_npc_id)

                if not merchant_inventory:
                    await ctx.connection.send_line(
                        colorize("This merchant has nothing to sell.", "YELLOW")
                    )
                    return

                # Find item by name
                template_result = await session.execute(
                    select(ItemTemplate).where(
                        ItemTemplate.id.in_(list(merchant_inventory.items.keys()))
                    )
                )
                templates = template_result.scalars().all()

                target_template = None
                for template in templates:
                    if item_name in template.name.lower():
                        target_template = template
                        break

                if not target_template:
                    await ctx.connection.send_line(
                        colorize(f"The merchant doesn't sell '{item_name}'.", "YELLOW")
                    )
                    return

                # Process the buy transaction
                success, message = await merchant_system.buy_item(
                    character, merchant_npc_id, target_template.id, quantity
                )

                # Refresh character to get updated gold
                await session.refresh(character)

                if success:
                    await ctx.connection.send_line(colorize(message, "GREEN"))
                    logger.info(
                        "item_purchased_via_command",
                        character_id=ctx.session.character_id,
                        character_name=character.name,
                        item_template_id=target_template.id,
                        quantity=quantity,
                    )
                else:
                    await ctx.connection.send_line(colorize(message, "YELLOW"))

        except Exception as e:
            logger.error("buy_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Failed to purchase item. Please try again.", "RED")
            )

    def _get_merchant_in_room(self, room_id: str) -> str | None:
        """Determine if there's a merchant in the current room."""
        room_to_merchant = {
            "imre_devi_shop": "merchant_imre",
            "imre_blacksmith": "blacksmith_imre",
            "imre_apothecary": "apothecary_imre",
            "university_bookshop": "bookshop_university",
            "imre_inn_waystone": "tavern_keeper",
        }
        return room_to_merchant.get(room_id)


class SellCommand(Command):
    """Sell an item to a merchant."""

    name = "sell"
    aliases = []
    help_text = "sell <item> [quantity] - Sell an item to the merchant"
    min_args = 1

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the sell command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        # Parse arguments
        quantity = 1
        item_name_parts = ctx.args

        # Check if last argument is a number
        if len(ctx.args) > 1 and ctx.args[-1].isdigit():
            quantity = int(ctx.args[-1])
            item_name_parts = ctx.args[:-1]

        item_name = " ".join(item_name_parts).lower()

        if quantity < 1:
            await ctx.connection.send_line(colorize("Quantity must be at least 1.", "YELLOW"))
            return

        try:
            async with get_session() as session:
                # Get character with items
                result = await session.execute(
                    select(Character)
                    .where(Character.id == UUID(ctx.session.character_id))
                    .options(joinedload(Character.items).joinedload(ItemInstance.template))
                )
                character = result.scalar_one_or_none()

                if not character:
                    await ctx.connection.send_line(colorize("Character not found.", "RED"))
                    return

                # Find merchant in room
                merchant_npc_id = self._get_merchant_in_room(character.current_room_id)

                if not merchant_npc_id:
                    await ctx.connection.send_line(colorize("There is no merchant here.", "YELLOW"))
                    return

                # Find item in inventory
                target_item = None
                for item_instance in character.items:
                    if (
                        item_instance.room_id is None
                        and item_name in item_instance.template.name.lower()
                    ):
                        target_item = item_instance
                        break

                if not target_item:
                    await ctx.connection.send_line(
                        colorize(f"You don't have '{item_name}' in your inventory.", "YELLOW")
                    )
                    return

                # Process the sell transaction
                success, message = await merchant_system.sell_item(
                    character, merchant_npc_id, str(target_item.id), quantity
                )

                # Refresh character to get updated gold
                await session.refresh(character)

                if success:
                    await ctx.connection.send_line(colorize(message, "GREEN"))
                    logger.info(
                        "item_sold_via_command",
                        character_id=ctx.session.character_id,
                        character_name=character.name,
                        item_id=str(target_item.id),
                        quantity=quantity,
                    )
                else:
                    await ctx.connection.send_line(colorize(message, "YELLOW"))

        except Exception as e:
            logger.error("sell_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Failed to sell item. Please try again.", "RED")
            )

    def _get_merchant_in_room(self, room_id: str) -> str | None:
        """Determine if there's a merchant in the current room."""
        room_to_merchant = {
            "imre_devi_shop": "merchant_imre",
            "imre_blacksmith": "blacksmith_imre",
            "imre_apothecary": "apothecary_imre",
            "university_bookshop": "bookshop_university",
            "imre_inn_waystone": "tavern_keeper",
        }
        return room_to_merchant.get(room_id)


class AppraiseCommand(Command):
    """Check buy and sell prices for an item."""

    name = "appraise"
    aliases = ["value"]
    help_text = "appraise <item> - Check buy and sell prices for an item"
    min_args = 1

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the appraise command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        item_name = " ".join(ctx.args).lower()

        try:
            async with get_session() as session:
                # Get character with items
                result = await session.execute(
                    select(Character)
                    .where(Character.id == UUID(ctx.session.character_id))
                    .options(joinedload(Character.items).joinedload(ItemInstance.template))
                )
                character = result.scalar_one_or_none()

                if not character:
                    await ctx.connection.send_line(colorize("Character not found.", "RED"))
                    return

                # Find merchant in room
                merchant_npc_id = self._get_merchant_in_room(character.current_room_id)

                if not merchant_npc_id:
                    await ctx.connection.send_line(colorize("There is no merchant here.", "YELLOW"))
                    return

                # Search for item in inventory
                target_item = None
                for item_instance in character.items:
                    if (
                        item_instance.room_id is None
                        and item_name in item_instance.template.name.lower()
                    ):
                        target_item = item_instance
                        break

                # If not in inventory, check merchant's shop
                if not target_item:
                    merchant_inventory = await merchant_system.get_merchant_inventory(
                        merchant_npc_id
                    )
                    if merchant_inventory:
                        template_result = await session.execute(
                            select(ItemTemplate).where(
                                ItemTemplate.id.in_(list(merchant_inventory.items.keys()))
                            )
                        )
                        templates = template_result.scalars().all()

                        for template in templates:
                            if item_name in template.name.lower():
                                # Found in merchant's shop
                                buy_price = merchant_system.calculate_buy_price(
                                    template.value, character
                                )
                                sell_price = merchant_system.calculate_sell_price(
                                    template.value, character
                                )

                                await ctx.connection.send_line("")
                                await ctx.connection.send_line(
                                    colorize(f"=== {template.name} ===", "CYAN")
                                )
                                await ctx.connection.send_line("")
                                await ctx.connection.send_line(
                                    f"Buy from merchant: {colorize(f'{buy_price} gold', 'YELLOW')}"
                                )
                                await ctx.connection.send_line(
                                    f"Sell to merchant:  {colorize(f'{sell_price} gold', 'GREEN')}"
                                )
                                return

                if not target_item:
                    await ctx.connection.send_line(
                        colorize(
                            f"You don't have '{item_name}' and the merchant doesn't sell it.",
                            "YELLOW",
                        )
                    )
                    return

                # Calculate prices for item in inventory
                assert target_item is not None  # Type narrowing for mypy
                item_template = target_item.template
                buy_price = merchant_system.calculate_buy_price(item_template.value, character)
                sell_price = merchant_system.calculate_sell_price(item_template.value, character)

                await ctx.connection.send_line("")
                await ctx.connection.send_line(colorize(f"=== {item_template.name} ===", "CYAN"))
                await ctx.connection.send_line("")
                await ctx.connection.send_line(
                    f"Buy from merchant: {colorize(f'{buy_price} gold', 'YELLOW')}"
                )
                await ctx.connection.send_line(
                    f"Sell to merchant:  {colorize(f'{sell_price} gold', 'GREEN')}"
                )

                if item_template.quest_item:
                    await ctx.connection.send_line("")
                    await ctx.connection.send_line(colorize("(Quest items cannot be sold)", "DIM"))

                logger.debug(
                    "item_appraised",
                    character_id=ctx.session.character_id,
                    item_name=item_template.name,
                )

        except Exception as e:
            logger.error("appraise_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Failed to appraise item. Please try again.", "RED")
            )

    def _get_merchant_in_room(self, room_id: str) -> str | None:
        """Determine if there's a merchant in the current room."""
        room_to_merchant = {
            "imre_devi_shop": "merchant_imre",
            "imre_blacksmith": "blacksmith_imre",
            "imre_apothecary": "apothecary_imre",
            "university_bookshop": "bookshop_university",
            "imre_inn_waystone": "tavern_keeper",
        }
        return room_to_merchant.get(room_id)
