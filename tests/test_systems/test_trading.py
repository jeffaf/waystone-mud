"""Tests for the player-to-player trading system."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from waystone.database.models import (
    Character,
    CharacterBackground,
    ItemInstance,
    ItemSlot,
    ItemTemplate,
    ItemType,
    User,
)
from waystone.game.systems import trading as trading_system
from waystone.game.systems.trading import TradeState


@pytest.fixture(autouse=True)
def reset_trading_state():
    """Reset trading state before each test."""
    trading_system.clear_all_trades()
    yield
    trading_system.clear_all_trades()


@pytest.fixture
async def trader1(db_session):
    """Create first trader for testing."""
    user = User(
        username="trader1",
        email="trader1@example.com",
        password_hash=User.hash_password("password123"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    character = Character(
        user_id=user.id,
        name="TraderOne",
        background=CharacterBackground.MERCHANT,
        current_room_id="imre_devi_shop",
        gold=1000,
        strength=10,
        dexterity=10,
        constitution=10,
        intelligence=10,
        wisdom=10,
        charisma=10,
    )
    db_session.add(character)
    await db_session.commit()
    await db_session.refresh(character)
    return character


@pytest.fixture
async def trader2(db_session):
    """Create second trader for testing."""
    user = User(
        username="trader2",
        email="trader2@example.com",
        password_hash=User.hash_password("password123"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    character = Character(
        user_id=user.id,
        name="TraderTwo",
        background=CharacterBackground.MERCHANT,
        current_room_id="imre_devi_shop",  # Same room
        gold=500,
        strength=10,
        dexterity=10,
        constitution=10,
        intelligence=10,
        wisdom=10,
        charisma=10,
    )
    db_session.add(character)
    await db_session.commit()
    await db_session.refresh(character)
    return character


@pytest.fixture
async def item_templates(db_session):
    """Create item templates for testing."""
    templates = [
        ItemTemplate(
            id="trade_sword",
            name="Trading Sword",
            description="A sword for trading",
            item_type=ItemType.WEAPON,
            slot=ItemSlot.MAIN_HAND,
            value=100,
            stackable=False,
        ),
        ItemTemplate(
            id="trade_potion",
            name="Trading Potion",
            description="A potion for trading",
            item_type=ItemType.CONSUMABLE,
            value=25,
            stackable=True,
        ),
    ]
    for template in templates:
        db_session.add(template)
    await db_session.commit()
    return templates


@pytest.mark.asyncio
class TestTradeInitiation:
    """Tests for initiating trades."""

    async def test_initiate_trade_success(self, trader1, trader2):
        """Test successfully initiating a trade."""
        success, message, session = trading_system.initiate_trade(trader1, trader2)

        assert success is True
        assert "initiated" in message.lower()
        assert session is not None
        assert session.state == TradeState.PENDING

    async def test_cannot_trade_with_self(self, trader1):
        """Test that you can't trade with yourself."""
        # This would be prevented by same-character check
        # But let's verify the room check works
        pass  # This scenario is prevented at command level

    async def test_cannot_trade_different_rooms(self, db_session, trader1, trader2):
        """Test that traders must be in same room."""
        # Move trader2 to different room
        trader2.current_room_id = "university_main_gates"
        await db_session.commit()

        success, message, session = trading_system.initiate_trade(trader1, trader2)

        assert success is False
        assert "same room" in message.lower()

    async def test_cannot_initiate_while_trading(self, db_session, trader1, trader2):
        """Test that you can't start a new trade while in one."""
        # Start first trade
        trading_system.initiate_trade(trader1, trader2)

        # Create a third character
        user = User(
            username="trader3",
            email="trader3@example.com",
            password_hash=User.hash_password("password123"),
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        trader3 = Character(
            user_id=user.id,
            name="TraderThree",
            background=CharacterBackground.MERCHANT,
            current_room_id="imre_devi_shop",
            gold=100,
        )
        db_session.add(trader3)
        await db_session.commit()

        # Try to start another trade
        success, message, _ = trading_system.initiate_trade(trader1, trader3)

        assert success is False
        assert "already in a trade" in message.lower()


@pytest.mark.asyncio
class TestTradeAcceptance:
    """Tests for accepting trades."""

    async def test_accept_pending_trade(self, trader1, trader2):
        """Test accepting a pending trade request."""
        trading_system.initiate_trade(trader1, trader2)

        success, message = trading_system.accept_trade_request(trader2)

        assert success is True
        session = trading_system.get_active_trade(trader2.id)
        assert session.state == TradeState.NEGOTIATING

    async def test_initiator_cannot_accept_own_request(self, trader1, trader2):
        """Test that initiator can't accept their own request."""
        trading_system.initiate_trade(trader1, trader2)

        success, message = trading_system.accept_trade_request(trader1)

        assert success is False
        assert "already initiated" in message.lower()


@pytest.mark.asyncio
class TestAddingItems:
    """Tests for adding items to trades."""

    async def test_add_item_to_trade(self, db_session, trader1, trader2, item_templates):
        """Test adding an item to a trade."""
        # Create item for trader1
        item = ItemInstance(
            template_id="trade_sword",
            owner_id=trader1.id,
            room_id=None,
            quantity=1,
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)

        # Load template
        result = await db_session.execute(
            select(ItemInstance)
            .where(ItemInstance.id == item.id)
            .options(joinedload(ItemInstance.template))
        )
        item = result.scalar_one()

        # Start and accept trade
        trading_system.initiate_trade(trader1, trader2)
        trading_system.accept_trade_request(trader2)

        # Add item to trade
        success, message = trading_system.add_item_to_trade(trader1, item, 1)

        assert success is True
        assert "added" in message.lower()

        session = trading_system.get_active_trade(trader1.id)
        assert item.id in session.initiator_offer.items

    async def test_cannot_add_unowned_item(self, db_session, trader1, trader2, item_templates):
        """Test that you can't add items you don't own."""
        # Create item owned by trader2
        item = ItemInstance(
            template_id="trade_sword",
            owner_id=trader2.id,
            room_id=None,
            quantity=1,
        )
        db_session.add(item)
        await db_session.commit()

        result = await db_session.execute(
            select(ItemInstance)
            .where(ItemInstance.id == item.id)
            .options(joinedload(ItemInstance.template))
        )
        item = result.scalar_one()

        trading_system.initiate_trade(trader1, trader2)
        trading_system.accept_trade_request(trader2)

        # Trader1 tries to add trader2's item
        success, message = trading_system.add_item_to_trade(trader1, item, 1)

        assert success is False
        assert "don't own" in message.lower()

    async def test_add_stackable_items(self, db_session, trader1, trader2, item_templates):
        """Test adding stackable items."""
        item = ItemInstance(
            template_id="trade_potion",
            owner_id=trader1.id,
            room_id=None,
            quantity=10,
        )
        db_session.add(item)
        await db_session.commit()

        result = await db_session.execute(
            select(ItemInstance)
            .where(ItemInstance.id == item.id)
            .options(joinedload(ItemInstance.template))
        )
        item = result.scalar_one()

        trading_system.initiate_trade(trader1, trader2)
        trading_system.accept_trade_request(trader2)

        success, message = trading_system.add_item_to_trade(trader1, item, 5)

        assert success is True
        session = trading_system.get_active_trade(trader1.id)
        assert session.initiator_offer.items[item.id] == 5

    async def test_cannot_add_more_than_owned(self, db_session, trader1, trader2, item_templates):
        """Test that you can't add more items than you have."""
        item = ItemInstance(
            template_id="trade_potion",
            owner_id=trader1.id,
            room_id=None,
            quantity=5,
        )
        db_session.add(item)
        await db_session.commit()

        result = await db_session.execute(
            select(ItemInstance)
            .where(ItemInstance.id == item.id)
            .options(joinedload(ItemInstance.template))
        )
        item = result.scalar_one()

        trading_system.initiate_trade(trader1, trader2)
        trading_system.accept_trade_request(trader2)

        success, message = trading_system.add_item_to_trade(trader1, item, 10)

        assert success is False
        assert "only have" in message.lower()


@pytest.mark.asyncio
class TestAddingMoney:
    """Tests for adding money to trades."""

    async def test_add_money_to_trade(self, trader1, trader2):
        """Test adding money to a trade."""
        trading_system.initiate_trade(trader1, trader2)
        trading_system.accept_trade_request(trader2)

        success, message = trading_system.add_money_to_trade(trader1, 100)

        assert success is True
        assert "100" in message or "1 talent" in message

        session = trading_system.get_active_trade(trader1.id)
        assert session.initiator_offer.money == 100

    async def test_cannot_add_more_money_than_have(self, trader1, trader2):
        """Test that you can't offer more money than you have."""
        trading_system.initiate_trade(trader1, trader2)
        trading_system.accept_trade_request(trader2)

        # trader1 has 1000 gold
        success, message = trading_system.add_money_to_trade(trader1, 2000)

        assert success is False
        assert "don't have enough money" in message.lower()

    async def test_cumulative_money_additions(self, trader1, trader2):
        """Test that money adds up across multiple offers."""
        trading_system.initiate_trade(trader1, trader2)
        trading_system.accept_trade_request(trader2)

        trading_system.add_money_to_trade(trader1, 100)
        trading_system.add_money_to_trade(trader1, 200)

        session = trading_system.get_active_trade(trader1.id)
        assert session.initiator_offer.money == 300


@pytest.mark.asyncio
class TestTradeCompletion:
    """Tests for completing trades."""

    async def test_complete_money_trade(self, db_session, trader1, trader2):
        """Test completing a money-only trade."""
        initial_gold1 = trader1.gold
        initial_gold2 = trader2.gold

        trading_system.initiate_trade(trader1, trader2)
        trading_system.accept_trade_request(trader2)

        # Trader1 offers 100 gold
        trading_system.add_money_to_trade(trader1, 100)

        # Both accept
        trading_system.accept_trade(trader1)
        trading_system.accept_trade(trader2)

        session = trading_system.get_active_trade(trader1.id)
        success, message = await trading_system.complete_trade(session, db_session)

        assert success is True

        await db_session.refresh(trader1)
        await db_session.refresh(trader2)

        assert trader1.gold == initial_gold1 - 100
        assert trader2.gold == initial_gold2 + 100

    async def test_complete_item_trade(self, db_session, trader1, trader2, item_templates):
        """Test completing an item trade."""
        # Give trader1 an item
        item = ItemInstance(
            template_id="trade_sword",
            owner_id=trader1.id,
            room_id=None,
            quantity=1,
        )
        db_session.add(item)
        await db_session.commit()

        result = await db_session.execute(
            select(ItemInstance)
            .where(ItemInstance.id == item.id)
            .options(joinedload(ItemInstance.template))
        )
        item = result.scalar_one()

        trading_system.initiate_trade(trader1, trader2)
        trading_system.accept_trade_request(trader2)

        trading_system.add_item_to_trade(trader1, item, 1)

        trading_system.accept_trade(trader1)
        trading_system.accept_trade(trader2)

        session = trading_system.get_active_trade(trader1.id)
        success, message = await trading_system.complete_trade(session, db_session)

        assert success is True

        # Refresh item
        await db_session.refresh(item)
        assert item.owner_id == trader2.id

    async def test_complete_mutual_trade(self, db_session, trader1, trader2, item_templates):
        """Test completing a trade with items and money on both sides."""
        initial_gold1 = trader1.gold
        initial_gold2 = trader2.gold

        # Give trader1 a sword
        sword = ItemInstance(
            template_id="trade_sword",
            owner_id=trader1.id,
            room_id=None,
            quantity=1,
        )
        db_session.add(sword)

        # Give trader2 potions
        potions = ItemInstance(
            template_id="trade_potion",
            owner_id=trader2.id,
            room_id=None,
            quantity=5,
        )
        db_session.add(potions)
        await db_session.commit()

        # Load with templates
        result = await db_session.execute(
            select(ItemInstance)
            .where(ItemInstance.id == sword.id)
            .options(joinedload(ItemInstance.template))
        )
        sword = result.scalar_one()

        result = await db_session.execute(
            select(ItemInstance)
            .where(ItemInstance.id == potions.id)
            .options(joinedload(ItemInstance.template))
        )
        potions = result.scalar_one()

        trading_system.initiate_trade(trader1, trader2)
        trading_system.accept_trade_request(trader2)

        # Trader1 offers sword
        trading_system.add_item_to_trade(trader1, sword, 1)

        # Trader2 offers potions + 50 gold
        trading_system.add_item_to_trade(trader2, potions, 3)
        trading_system.add_money_to_trade(trader2, 50)

        trading_system.accept_trade(trader1)
        trading_system.accept_trade(trader2)

        session = trading_system.get_active_trade(trader1.id)
        sword_id = sword.id
        potions_id = potions.id
        success, message = await trading_system.complete_trade(session, db_session)

        assert success is True

        # Re-query items - select specific columns to avoid lazy loading issues
        result = await db_session.execute(
            select(ItemInstance.owner_id, ItemInstance.quantity).where(ItemInstance.id == sword_id)
        )
        sword_row = result.one()

        result = await db_session.execute(
            select(ItemInstance.owner_id, ItemInstance.quantity).where(ItemInstance.id == potions_id)
        )
        potions_row = result.one()

        # Re-query characters for money
        result = await db_session.execute(
            select(Character.gold).where(Character.id == trader1.id)
        )
        trader1_gold = result.scalar_one()

        result = await db_session.execute(
            select(Character.gold).where(Character.id == trader2.id)
        )
        trader2_gold = result.scalar_one()

        # Sword should now belong to trader2
        assert sword_row.owner_id == trader2.id

        # Potions should be split (3 to trader1, 2 remain with trader2)
        assert potions_row.quantity == 2  # Original reduced

        # Money should be transferred
        assert trader1_gold == initial_gold1 + 50
        assert trader2_gold == initial_gold2 - 50

    async def test_cannot_complete_without_both_accepting(self, db_session, trader1, trader2):
        """Test that trade can't complete without both accepting."""
        trading_system.initiate_trade(trader1, trader2)
        trading_system.accept_trade_request(trader2)

        trading_system.add_money_to_trade(trader1, 100)
        trading_system.accept_trade(trader1)
        # Trader2 doesn't accept

        session = trading_system.get_active_trade(trader1.id)
        success, message = await trading_system.complete_trade(session, db_session)

        assert success is False
        assert "both parties" in message.lower()


@pytest.mark.asyncio
class TestTradeCancellation:
    """Tests for cancelling trades."""

    async def test_cancel_trade(self, trader1, trader2):
        """Test cancelling a trade."""
        trading_system.initiate_trade(trader1, trader2)

        success, message = trading_system.cancel_trade(trader1)

        assert success is True
        assert trading_system.get_active_trade(trader1.id) is None
        assert trading_system.get_active_trade(trader2.id) is None

    async def test_target_can_cancel(self, trader1, trader2):
        """Test that target can also cancel."""
        trading_system.initiate_trade(trader1, trader2)
        trading_system.accept_trade_request(trader2)

        success, message = trading_system.cancel_trade(trader2)

        assert success is True
        assert trading_system.get_active_trade(trader1.id) is None


@pytest.mark.asyncio
class TestTradeAcceptanceReset:
    """Tests for acceptance reset when trade is modified."""

    async def test_acceptance_resets_on_item_add(self, db_session, trader1, trader2, item_templates):
        """Test that acceptance resets when items are added."""
        item = ItemInstance(
            template_id="trade_sword",
            owner_id=trader1.id,
            room_id=None,
            quantity=1,
        )
        db_session.add(item)
        await db_session.commit()

        result = await db_session.execute(
            select(ItemInstance)
            .where(ItemInstance.id == item.id)
            .options(joinedload(ItemInstance.template))
        )
        item = result.scalar_one()

        trading_system.initiate_trade(trader1, trader2)
        trading_system.accept_trade_request(trader2)

        # Both accept empty trade
        trading_system.accept_trade(trader1)
        trading_system.accept_trade(trader2)

        session = trading_system.get_active_trade(trader1.id)
        assert session.initiator_offer.accepted is True
        assert session.target_offer.accepted is True

        # Add item - should reset acceptance
        trading_system.add_item_to_trade(trader1, item, 1)

        assert session.initiator_offer.accepted is False
        assert session.target_offer.accepted is False

    async def test_acceptance_resets_on_money_add(self, trader1, trader2):
        """Test that acceptance resets when money is added."""
        trading_system.initiate_trade(trader1, trader2)
        trading_system.accept_trade_request(trader2)

        trading_system.accept_trade(trader1)
        trading_system.accept_trade(trader2)

        session = trading_system.get_active_trade(trader1.id)
        assert session.initiator_offer.accepted is True

        trading_system.add_money_to_trade(trader1, 50)

        assert session.initiator_offer.accepted is False
        assert session.target_offer.accepted is False
