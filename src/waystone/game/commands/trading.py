"""Trading commands for Waystone MUD."""

from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from waystone.database.engine import get_session
from waystone.database.models import Character, ItemInstance
from waystone.game.systems import trading as trading_system
from waystone.game.systems.economy import format_money, parse_money
from waystone.network import colorize

from .base import Command, CommandContext

logger = structlog.get_logger(__name__)


class TradeCommand(Command):
    """Initiate or show trade status."""

    name = "trade"
    aliases = []
    help_text = "trade <player> - Initiate a trade with another player"
    min_args = 0

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the trade command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        try:
            async with get_session() as session:
                # Get current character
                result = await session.execute(
                    select(Character).where(Character.id == UUID(ctx.session.character_id))
                )
                character = result.scalar_one_or_none()

                if not character:
                    await ctx.connection.send_line(colorize("Character not found.", "RED"))
                    return

                # No arguments - show current trade status
                if not ctx.args:
                    trade_session = trading_system.get_active_trade(character.id)
                    if trade_session:
                        status = trading_system.format_trade_status(trade_session, character.id)
                        await ctx.connection.send_line(colorize(status, "CYAN"))
                    else:
                        await ctx.connection.send_line(
                            colorize("You are not in a trade. Use 'trade <player>' to start one.", "YELLOW")
                        )
                    return

                # Find target player
                target_name = " ".join(ctx.args)

                # Check if it's a pending trade acceptance
                existing_trade = trading_system.get_active_trade(character.id)
                if existing_trade and existing_trade.state == trading_system.TradeState.PENDING:
                    if character.id == existing_trade.target_id:
                        # This is the target accepting the trade
                        success, message = trading_system.accept_trade_request(character)
                        if success:
                            await ctx.connection.send_line(colorize(message, "GREEN"))
                        else:
                            await ctx.connection.send_line(colorize(message, "YELLOW"))
                        return

                # Find the target character in the same room
                result = await session.execute(
                    select(Character).where(
                        Character.name.ilike(f"%{target_name}%"),
                        Character.current_room_id == character.current_room_id,
                        Character.id != character.id,
                    )
                )
                target = result.scalar_one_or_none()

                if not target:
                    await ctx.connection.send_line(
                        colorize(f"No player named '{target_name}' found in this room.", "YELLOW")
                    )
                    return

                # Initiate the trade
                success, message, trade_session = trading_system.initiate_trade(character, target)

                if success:
                    await ctx.connection.send_line(colorize(message, "GREEN"))
                    await ctx.connection.send_line(
                        colorize("Waiting for them to accept. They can type 'trade accept'.", "DIM")
                    )

                    # Notify the target (would need engine broadcast in production)
                    logger.info(
                        "trade_invitation_sent",
                        initiator=character.name,
                        target=target.name,
                        trade_id=trade_session.id if trade_session else None,
                    )
                else:
                    await ctx.connection.send_line(colorize(message, "YELLOW"))

        except Exception as e:
            logger.error("trade_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Failed to process trade command. Please try again.", "RED")
            )


class TradeAcceptCommand(Command):
    """Accept a pending trade request or accept current trade terms."""

    name = "accept"
    aliases = []
    help_text = "accept - Accept pending trade request or current trade terms"
    min_args = 0

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the accept command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        try:
            async with get_session() as session:
                result = await session.execute(
                    select(Character).where(Character.id == UUID(ctx.session.character_id))
                )
                character = result.scalar_one_or_none()

                if not character:
                    await ctx.connection.send_line(colorize("Character not found.", "RED"))
                    return

                trade_session = trading_system.get_active_trade(character.id)
                if not trade_session:
                    await ctx.connection.send_line(
                        colorize("You don't have any pending trade requests.", "YELLOW")
                    )
                    return

                # If pending, accept the trade request
                if trade_session.state == trading_system.TradeState.PENDING:
                    if character.id == trade_session.target_id:
                        success, message = trading_system.accept_trade_request(character)
                        if success:
                            await ctx.connection.send_line(colorize(message, "GREEN"))
                        else:
                            await ctx.connection.send_line(colorize(message, "YELLOW"))
                    else:
                        await ctx.connection.send_line(
                            colorize("Waiting for the other player to accept your trade request.", "YELLOW")
                        )
                    return

                # Otherwise, accept trade terms
                success, message = trading_system.accept_trade(character)
                if success:
                    await ctx.connection.send_line(colorize(message, "GREEN"))

                    # Check if both accepted
                    if trade_session.both_accepted():
                        await ctx.connection.send_line(
                            colorize("Both parties have accepted! Completing trade...", "CYAN")
                        )
                        complete_success, complete_message = await trading_system.complete_trade(
                            trade_session, session
                        )
                        if complete_success:
                            await ctx.connection.send_line(colorize(complete_message, "GREEN"))
                        else:
                            await ctx.connection.send_line(colorize(complete_message, "RED"))
                else:
                    await ctx.connection.send_line(colorize(message, "YELLOW"))

        except Exception as e:
            logger.error("accept_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Failed to accept trade. Please try again.", "RED")
            )


class OfferCommand(Command):
    """Add items or money to your trade offer."""

    name = "offer"
    aliases = []
    help_text = "offer <item> [quantity] or offer <amount> money - Add to trade"
    min_args = 1

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the offer command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        try:
            async with get_session() as session:
                result = await session.execute(
                    select(Character)
                    .where(Character.id == UUID(ctx.session.character_id))
                    .options(joinedload(Character.items).joinedload(ItemInstance.template))
                )
                character = result.unique().scalar_one_or_none()

                if not character:
                    await ctx.connection.send_line(colorize("Character not found.", "RED"))
                    return

                trade_session = trading_system.get_active_trade(character.id)
                if not trade_session:
                    await ctx.connection.send_line(
                        colorize("You are not in a trade.", "YELLOW")
                    )
                    return

                # Check for "money" keyword
                if ctx.args[-1].lower() == "money":
                    # Parse money amount
                    money_str = " ".join(ctx.args[:-1])
                    amount = parse_money(money_str)
                    if amount is None:
                        await ctx.connection.send_line(
                            colorize(f"Invalid amount: '{money_str}'", "YELLOW")
                        )
                        return

                    success, message = trading_system.add_money_to_trade(character, amount)
                    if success:
                        await ctx.connection.send_line(colorize(message, "GREEN"))
                    else:
                        await ctx.connection.send_line(colorize(message, "YELLOW"))
                    return

                # Parse quantity if last arg is a number
                quantity = 1
                item_name_parts = ctx.args

                if len(ctx.args) > 1 and ctx.args[-1].isdigit():
                    quantity = int(ctx.args[-1])
                    item_name_parts = ctx.args[:-1]

                item_name = " ".join(item_name_parts).lower()

                if quantity < 1:
                    await ctx.connection.send_line(
                        colorize("Quantity must be at least 1.", "YELLOW")
                    )
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

                success, message = trading_system.add_item_to_trade(
                    character, target_item, quantity
                )
                if success:
                    await ctx.connection.send_line(colorize(message, "GREEN"))
                else:
                    await ctx.connection.send_line(colorize(message, "YELLOW"))

        except Exception as e:
            logger.error("offer_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Failed to add offer. Please try again.", "RED")
            )


class RemoveOfferCommand(Command):
    """Remove items or money from your trade offer."""

    name = "remove"
    aliases = ["unoff", "unoffer"]
    help_text = "remove <item> or remove <amount> money - Remove from trade"
    min_args = 1

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the remove command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        try:
            async with get_session() as session:
                result = await session.execute(
                    select(Character)
                    .where(Character.id == UUID(ctx.session.character_id))
                    .options(joinedload(Character.items).joinedload(ItemInstance.template))
                )
                character = result.unique().scalar_one_or_none()

                if not character:
                    await ctx.connection.send_line(colorize("Character not found.", "RED"))
                    return

                trade_session = trading_system.get_active_trade(character.id)
                if not trade_session:
                    await ctx.connection.send_line(
                        colorize("You are not in a trade.", "YELLOW")
                    )
                    return

                # Check for "money" keyword
                if ctx.args[-1].lower() == "money":
                    money_str = " ".join(ctx.args[:-1])
                    amount = parse_money(money_str)
                    if amount is None:
                        await ctx.connection.send_line(
                            colorize(f"Invalid amount: '{money_str}'", "YELLOW")
                        )
                        return

                    success, message = trading_system.remove_from_trade(
                        character, item=None, money_amount=amount
                    )
                    if success:
                        await ctx.connection.send_line(colorize(message, "GREEN"))
                    else:
                        await ctx.connection.send_line(colorize(message, "YELLOW"))
                    return

                # Find item in inventory
                item_name = " ".join(ctx.args).lower()
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

                success, message = trading_system.remove_from_trade(character, item=target_item)
                if success:
                    await ctx.connection.send_line(colorize(message, "GREEN"))
                else:
                    await ctx.connection.send_line(colorize(message, "YELLOW"))

        except Exception as e:
            logger.error("remove_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Failed to remove from offer. Please try again.", "RED")
            )


class CancelTradeCommand(Command):
    """Cancel the current trade."""

    name = "cancel"
    aliases = ["decline"]
    help_text = "cancel - Cancel the current trade"
    min_args = 0

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the cancel command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        try:
            async with get_session() as session:
                result = await session.execute(
                    select(Character).where(Character.id == UUID(ctx.session.character_id))
                )
                character = result.scalar_one_or_none()

                if not character:
                    await ctx.connection.send_line(colorize("Character not found.", "RED"))
                    return

                success, message = trading_system.cancel_trade(character)
                if success:
                    await ctx.connection.send_line(colorize(message, "GREEN"))
                else:
                    await ctx.connection.send_line(colorize(message, "YELLOW"))

        except Exception as e:
            logger.error("cancel_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Failed to cancel trade. Please try again.", "RED")
            )
