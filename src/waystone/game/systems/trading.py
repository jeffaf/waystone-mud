"""Player-to-player trading system for Waystone MUD."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import UUID

import structlog

from waystone.database.models import Character, ItemInstance
from waystone.game.systems.economy import format_money

logger = structlog.get_logger(__name__)


class TradeState(Enum):
    """State of a trade session."""

    PENDING = "pending"  # Trade initiated, waiting for other player
    NEGOTIATING = "negotiating"  # Both players in trade, adding items
    ACCEPTED_INITIATOR = "accepted_initiator"  # Initiator accepted, waiting for target
    ACCEPTED_TARGET = "accepted_target"  # Target accepted, waiting for initiator
    COMPLETED = "completed"  # Trade finished successfully
    CANCELLED = "cancelled"  # Trade was cancelled


@dataclass
class TradeOffer:
    """Items and money offered by one party in a trade."""

    character_id: UUID
    items: dict[UUID, int] = field(default_factory=dict)  # item_id -> quantity
    money: int = 0  # amount in drabs
    accepted: bool = False


@dataclass
class TradeSession:
    """A trade session between two players."""

    id: str
    initiator_id: UUID
    target_id: UUID
    initiator_offer: TradeOffer
    target_offer: TradeOffer
    state: TradeState = TradeState.PENDING
    created_at: datetime = field(default_factory=datetime.now)

    def get_offer_for(self, character_id: UUID) -> TradeOffer | None:
        """Get the offer for a specific character."""
        if character_id == self.initiator_id:
            return self.initiator_offer
        elif character_id == self.target_id:
            return self.target_offer
        return None

    def get_other_offer(self, character_id: UUID) -> TradeOffer | None:
        """Get the other party's offer."""
        if character_id == self.initiator_id:
            return self.target_offer
        elif character_id == self.target_id:
            return self.initiator_offer
        return None

    def is_participant(self, character_id: UUID) -> bool:
        """Check if character is part of this trade."""
        return character_id in (self.initiator_id, self.target_id)

    def both_accepted(self) -> bool:
        """Check if both parties have accepted."""
        return self.initiator_offer.accepted and self.target_offer.accepted


# Global store of active trade sessions
# In production, this should be in Redis for multi-server support
_active_trades: dict[str, TradeSession] = {}
_character_trades: dict[UUID, str] = {}  # character_id -> trade_id


def generate_trade_id() -> str:
    """Generate a unique trade ID."""
    import uuid

    return f"trade_{uuid.uuid4().hex[:8]}"


def get_active_trade(character_id: UUID) -> TradeSession | None:
    """Get the active trade session for a character."""
    trade_id = _character_trades.get(character_id)
    if trade_id:
        return _active_trades.get(trade_id)
    return None


def initiate_trade(
    initiator: Character, target: Character
) -> tuple[bool, str, TradeSession | None]:
    """
    Start a trade between two characters.

    Args:
        initiator: Character starting the trade
        target: Character being invited to trade

    Returns:
        Tuple of (success, message, trade_session)
    """
    # Check if either party is already in a trade
    if get_active_trade(initiator.id):
        return False, "You are already in a trade. Use 'cancel' to end it first.", None

    if get_active_trade(target.id):
        return False, f"{target.name} is already in a trade.", None

    # Check if they're in the same room
    if initiator.current_room_id != target.current_room_id:
        return False, "You must be in the same room to trade.", None

    # Create the trade session
    trade_id = generate_trade_id()
    session = TradeSession(
        id=trade_id,
        initiator_id=initiator.id,
        target_id=target.id,
        initiator_offer=TradeOffer(character_id=initiator.id),
        target_offer=TradeOffer(character_id=target.id),
        state=TradeState.PENDING,
    )

    _active_trades[trade_id] = session
    _character_trades[initiator.id] = trade_id
    _character_trades[target.id] = trade_id

    logger.info(
        "trade_initiated",
        trade_id=trade_id,
        initiator_id=str(initiator.id),
        initiator_name=initiator.name,
        target_id=str(target.id),
        target_name=target.name,
    )

    return True, f"You have initiated a trade with {target.name}.", session


def accept_trade_request(character: Character) -> tuple[bool, str]:
    """
    Accept a pending trade request.

    Args:
        character: Character accepting the trade

    Returns:
        Tuple of (success, message)
    """
    session = get_active_trade(character.id)
    if not session:
        return False, "You don't have any pending trade requests."

    if session.state != TradeState.PENDING:
        return False, "This trade is already in progress."

    if character.id != session.target_id:
        return False, "You already initiated this trade."

    session.state = TradeState.NEGOTIATING

    logger.info(
        "trade_accepted",
        trade_id=session.id,
        character_id=str(character.id),
        character_name=character.name,
    )

    return (
        True,
        "Trade accepted. Use 'offer <item>' to add items or 'offer <amount> money' to add money.",
    )


def add_item_to_trade(
    character: Character, item: ItemInstance, quantity: int = 1
) -> tuple[bool, str]:
    """
    Add an item to the character's trade offer.

    Args:
        character: Character offering the item
        item: Item instance to offer
        quantity: Number to offer

    Returns:
        Tuple of (success, message)
    """
    session = get_active_trade(character.id)
    if not session:
        return False, "You are not in a trade."

    if session.state not in (TradeState.NEGOTIATING, TradeState.PENDING):
        return False, "You can't modify the trade at this point."

    # Reset acceptance if modifying trade
    session.initiator_offer.accepted = False
    session.target_offer.accepted = False

    # Verify ownership
    if item.owner_id != character.id:
        return False, "You don't own that item."

    if item.room_id is not None:
        return False, "That item is not in your inventory."

    # Check quantity
    if item.quantity < quantity:
        return False, f"You only have {item.quantity} of that item."

    # Check if item is already in trade
    offer = session.get_offer_for(character.id)
    if not offer:
        return False, "Trade error: offer not found."

    current_offered = offer.items.get(item.id, 0)
    if current_offered + quantity > item.quantity:
        return False, f"You can't offer more than you have. Already offering {current_offered}."

    # Add to trade
    offer.items[item.id] = current_offered + quantity

    logger.info(
        "trade_item_added",
        trade_id=session.id,
        character_id=str(character.id),
        item_id=str(item.id),
        quantity=quantity,
    )

    return True, f"Added {quantity}x {item.template.name if item.template else 'item'} to trade."


def add_money_to_trade(character: Character, amount: int) -> tuple[bool, str]:
    """
    Add money to the character's trade offer.

    Args:
        character: Character offering money
        amount: Amount in drabs to offer

    Returns:
        Tuple of (success, message)
    """
    session = get_active_trade(character.id)
    if not session:
        return False, "You are not in a trade."

    if session.state not in (TradeState.NEGOTIATING, TradeState.PENDING):
        return False, "You can't modify the trade at this point."

    # Reset acceptance if modifying trade
    session.initiator_offer.accepted = False
    session.target_offer.accepted = False

    if amount < 0:
        return False, "Amount must be positive."

    offer = session.get_offer_for(character.id)
    if not offer:
        return False, "Trade error: offer not found."

    total_offered = offer.money + amount
    if total_offered > character.money:
        return (
            False,
            f"You don't have enough money. You have {format_money(character.money)}.",
        )

    offer.money = total_offered

    logger.info(
        "trade_money_added",
        trade_id=session.id,
        character_id=str(character.id),
        amount=amount,
    )

    return True, f"Added {format_money(amount)} to trade. Total: {format_money(total_offered)}."


def remove_from_trade(
    character: Character, item: ItemInstance | None = None, money_amount: int = 0
) -> tuple[bool, str]:
    """
    Remove an item or money from the character's trade offer.

    Args:
        character: Character removing from offer
        item: Item instance to remove (or None)
        money_amount: Money amount to remove (or 0)

    Returns:
        Tuple of (success, message)
    """
    session = get_active_trade(character.id)
    if not session:
        return False, "You are not in a trade."

    if session.state not in (TradeState.NEGOTIATING, TradeState.PENDING):
        return False, "You can't modify the trade at this point."

    # Reset acceptance if modifying trade
    session.initiator_offer.accepted = False
    session.target_offer.accepted = False

    offer = session.get_offer_for(character.id)
    if not offer:
        return False, "Trade error: offer not found."

    if item:
        if item.id not in offer.items:
            return False, "That item is not in your trade offer."
        del offer.items[item.id]
        return True, f"Removed {item.template.name if item.template else 'item'} from trade."

    if money_amount > 0:
        if money_amount > offer.money:
            money_amount = offer.money
        offer.money -= money_amount
        return True, f"Removed {format_money(money_amount)} from trade."

    return False, "Specify an item or money amount to remove."


def accept_trade(character: Character) -> tuple[bool, str]:
    """
    Accept the current trade terms.

    Args:
        character: Character accepting the trade

    Returns:
        Tuple of (success, message)
    """
    session = get_active_trade(character.id)
    if not session:
        return False, "You are not in a trade."

    if session.state not in (TradeState.NEGOTIATING, TradeState.PENDING):
        return False, "Cannot accept trade in current state."

    offer = session.get_offer_for(character.id)
    if not offer:
        return False, "Trade error: offer not found."

    offer.accepted = True

    logger.info(
        "trade_terms_accepted",
        trade_id=session.id,
        character_id=str(character.id),
    )

    return True, "You have accepted the trade terms. Waiting for the other player."


def cancel_trade(character: Character) -> tuple[bool, str]:
    """
    Cancel the current trade.

    Args:
        character: Character cancelling the trade

    Returns:
        Tuple of (success, message)
    """
    session = get_active_trade(character.id)
    if not session:
        return False, "You are not in a trade."

    session.state = TradeState.CANCELLED

    # Remove from tracking
    if session.initiator_id in _character_trades:
        del _character_trades[session.initiator_id]
    if session.target_id in _character_trades:
        del _character_trades[session.target_id]
    if session.id in _active_trades:
        del _active_trades[session.id]

    logger.info(
        "trade_cancelled",
        trade_id=session.id,
        cancelled_by=str(character.id),
    )

    return True, "Trade cancelled."


async def complete_trade(session: TradeSession, db_session) -> tuple[bool, str]:
    """
    Complete the trade, transferring items and money.

    This is the atomic operation that executes the trade.

    Args:
        session: The trade session to complete
        db_session: Database session for transaction

    Returns:
        Tuple of (success, message)
    """
    from sqlalchemy import select
    from sqlalchemy.orm import joinedload

    if not session.both_accepted():
        return False, "Both parties must accept before completing the trade."

    try:
        # Load both characters with their items
        result = await db_session.execute(
            select(Character)
            .where(Character.id == session.initiator_id)
            .options(joinedload(Character.items))
        )
        initiator = result.unique().scalar_one_or_none()

        result = await db_session.execute(
            select(Character)
            .where(Character.id == session.target_id)
            .options(joinedload(Character.items))
        )
        target = result.unique().scalar_one_or_none()

        if not initiator or not target:
            return False, "One of the trade participants is no longer available."

        initiator_offer = session.initiator_offer
        target_offer = session.target_offer

        # Validate initiator has enough money
        if initiator.money < initiator_offer.money:
            return False, f"{initiator.name} doesn't have enough money."

        # Validate target has enough money
        if target.money < target_offer.money:
            return False, f"{target.name} doesn't have enough money."

        # Validate all items exist and have correct quantities
        for item_id, quantity in initiator_offer.items.items():
            result = await db_session.execute(
                select(ItemInstance)
                .where(ItemInstance.id == item_id)
                .options(joinedload(ItemInstance.template))
            )
            item = result.scalar_one_or_none()
            if not item or item.owner_id != initiator.id or item.quantity < quantity:
                return False, f"{initiator.name} no longer has the offered items."

        for item_id, quantity in target_offer.items.items():
            result = await db_session.execute(
                select(ItemInstance)
                .where(ItemInstance.id == item_id)
                .options(joinedload(ItemInstance.template))
            )
            item = result.scalar_one_or_none()
            if not item or item.owner_id != target.id or item.quantity < quantity:
                return False, f"{target.name} no longer has the offered items."

        # Transfer money
        initiator.money -= initiator_offer.money
        initiator.money += target_offer.money
        target.money -= target_offer.money
        target.money += initiator_offer.money

        # Transfer items from initiator to target
        for item_id, quantity in initiator_offer.items.items():
            result = await db_session.execute(
                select(ItemInstance)
                .where(ItemInstance.id == item_id)
                .options(joinedload(ItemInstance.template))
            )
            item = result.scalar_one_or_none()
            if item:
                if item.quantity == quantity:
                    # Transfer entire item
                    item.owner_id = target.id
                else:
                    # Split stack - reduce original and create new
                    item.quantity -= quantity
                    new_item = ItemInstance(
                        template_id=item.template_id,
                        owner_id=target.id,
                        room_id=None,
                        quantity=quantity,
                    )
                    db_session.add(new_item)

        # Transfer items from target to initiator
        for item_id, quantity in target_offer.items.items():
            result = await db_session.execute(
                select(ItemInstance)
                .where(ItemInstance.id == item_id)
                .options(joinedload(ItemInstance.template))
            )
            item = result.scalar_one_or_none()
            if item:
                if item.quantity == quantity:
                    # Transfer entire item
                    item.owner_id = initiator.id
                else:
                    # Split stack
                    item.quantity -= quantity
                    new_item = ItemInstance(
                        template_id=item.template_id,
                        owner_id=initiator.id,
                        room_id=None,
                        quantity=quantity,
                    )
                    db_session.add(new_item)

        await db_session.commit()

        session.state = TradeState.COMPLETED

        # Clean up tracking
        if session.initiator_id in _character_trades:
            del _character_trades[session.initiator_id]
        if session.target_id in _character_trades:
            del _character_trades[session.target_id]
        if session.id in _active_trades:
            del _active_trades[session.id]

        logger.info(
            "trade_completed",
            trade_id=session.id,
            initiator_id=str(session.initiator_id),
            target_id=str(session.target_id),
            initiator_items=len(initiator_offer.items),
            initiator_money=initiator_offer.money,
            target_items=len(target_offer.items),
            target_money=target_offer.money,
        )

        return True, "Trade completed successfully!"

    except Exception as e:
        await db_session.rollback()
        logger.error(
            "trade_completion_failed",
            trade_id=session.id,
            error=str(e),
            exc_info=True,
        )
        return False, "Trade failed due to an error. Please try again."


def format_trade_status(session: TradeSession, viewer_id: UUID) -> str:
    """
    Format the current trade status for display.

    Args:
        session: The trade session
        viewer_id: ID of the character viewing the status

    Returns:
        Formatted string showing trade status
    """
    lines = ["=== Trade Status ===", ""]

    _is_initiator = viewer_id == session.initiator_id

    # Your offer
    your_offer = session.get_offer_for(viewer_id)
    their_offer = session.get_other_offer(viewer_id)

    lines.append("Your Offer:")
    if your_offer:
        if your_offer.items:
            for item_id, qty in your_offer.items.items():
                lines.append(f"  - {qty}x item (ID: {str(item_id)[:8]})")
        if your_offer.money > 0:
            lines.append(f"  - {format_money(your_offer.money)}")
        if not your_offer.items and your_offer.money == 0:
            lines.append("  (nothing)")
        lines.append(f"  Status: {'ACCEPTED' if your_offer.accepted else 'Not accepted'}")
    lines.append("")

    lines.append("Their Offer:")
    if their_offer:
        if their_offer.items:
            for item_id, qty in their_offer.items.items():
                lines.append(f"  - {qty}x item (ID: {str(item_id)[:8]})")
        if their_offer.money > 0:
            lines.append(f"  - {format_money(their_offer.money)}")
        if not their_offer.items and their_offer.money == 0:
            lines.append("  (nothing)")
        lines.append(f"  Status: {'ACCEPTED' if their_offer.accepted else 'Not accepted'}")

    lines.append("")
    lines.append(f"Trade State: {session.state.value}")

    return "\n".join(lines)


def clear_all_trades() -> None:
    """Clear all active trades. Used for testing."""
    _active_trades.clear()
    _character_trades.clear()
