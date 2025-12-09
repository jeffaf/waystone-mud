"""Tests for the merchant/shop system."""

import pytest
from sqlalchemy import select

from waystone.database.models import (
    Character,
    CharacterBackground,
    ItemInstance,
    ItemSlot,
    ItemTemplate,
    ItemType,
)
from waystone.game.systems import merchant as merchant_system


@pytest.fixture
async def sample_character(db_session, sample_user):
    """Create a sample character for testing."""
    character = Character(
        user_id=sample_user.id,
        name="TestBuyer",
        background=CharacterBackground.MERCHANT,
        current_room_id="imre_devi_shop",
        gold=500,  # Start with 500 gold
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
    """Create sample item templates for testing."""
    templates = [
        ItemTemplate(
            id="bread",
            name="Loaf of Bread",
            description="A fresh loaf of bread",
            item_type=ItemType.CONSUMABLE,
            value=5,
            stackable=True,
        ),
        ItemTemplate(
            id="health_potion",
            name="Health Potion",
            description="A red potion that restores health",
            item_type=ItemType.CONSUMABLE,
            value=50,
            stackable=True,
        ),
        ItemTemplate(
            id="iron_sword",
            name="Iron Sword",
            description="A sturdy iron sword",
            item_type=ItemType.WEAPON,
            slot=ItemSlot.MAIN_HAND,
            value=100,
            stackable=False,
        ),
        ItemTemplate(
            id="quest_item",
            name="Ancient Scroll",
            description="An important quest item",
            item_type=ItemType.QUEST,
            value=0,
            stackable=False,
            quest_item=True,
        ),
    ]

    for template in templates:
        db_session.add(template)
    await db_session.commit()

    return templates


@pytest.mark.asyncio
class TestMerchantInventory:
    """Test merchant inventory loading and management."""

    async def test_load_merchant_inventories(self):
        """Test loading merchant inventories from YAML."""
        # Reload to ensure fresh data
        merchant_system.load_merchant_inventories()

        # Check that merchants are loaded
        merchant_imre = await merchant_system.get_merchant_inventory("merchant_imre")
        assert merchant_imre is not None
        assert merchant_imre.npc_id == "merchant_imre"
        assert merchant_imre.gold == 500
        assert "bread" in merchant_imre.items

    async def test_get_nonexistent_merchant(self):
        """Test getting inventory for non-existent merchant."""
        inventory = await merchant_system.get_merchant_inventory("nonexistent_merchant")
        assert inventory is None


@pytest.mark.asyncio
class TestPriceCalculations:
    """Test price calculation functions."""

    async def test_calculate_buy_price(self, sample_character):
        """Test buy price calculation."""
        base_value = 100
        buy_price = merchant_system.calculate_buy_price(base_value, sample_character)
        # Currently, buy price equals base value
        assert buy_price == 100

    async def test_calculate_sell_price(self, sample_character):
        """Test sell price calculation (50% of base)."""
        base_value = 100
        sell_price = merchant_system.calculate_sell_price(base_value, sample_character)
        # Sell price should be 50% of base value
        assert sell_price == 50


@pytest.mark.asyncio
class TestBuyingItems:
    """Test buying items from merchants."""

    async def test_buy_single_item(self, db_session, sample_character, item_templates):
        """Test buying a single item."""
        success, message = await merchant_system.buy_item(
            sample_character, "merchant_imre", "bread", 1, session=db_session
        )

        assert success is True
        assert "bought" in message.lower()

        # Refresh character
        await db_session.refresh(sample_character)

        # Check gold was deducted (bread costs 5 gold)
        assert sample_character.gold == 495

        # Check item was added to inventory
        result = await db_session.execute(
            select(ItemInstance)
            .where(ItemInstance.owner_id == sample_character.id)
            .where(ItemInstance.template_id == "bread")
        )
        item = result.scalar_one_or_none()
        assert item is not None
        assert item.quantity == 1

    async def test_buy_multiple_items(self, db_session, sample_character, item_templates):
        """Test buying multiple items at once."""
        success, message = await merchant_system.buy_item(
            sample_character, "merchant_imre", "bread", 5, session=db_session
        )

        assert success is True

        # Refresh character
        await db_session.refresh(sample_character)

        # Check gold was deducted (5 bread at 5 gold each = 25 gold)
        assert sample_character.gold == 475

        # Check items were added
        result = await db_session.execute(
            select(ItemInstance)
            .where(ItemInstance.owner_id == sample_character.id)
            .where(ItemInstance.template_id == "bread")
        )
        item = result.scalar_one_or_none()
        assert item is not None
        assert item.quantity == 5  # Should be stacked

    async def test_buy_insufficient_gold(self, db_session, sample_character, item_templates):
        """Test buying item without enough gold."""
        # Set character gold very low so they can't afford even 1 sword (cost 100)
        sample_character.gold = 50
        await db_session.commit()

        # Try to buy one iron sword (costs 100 gold)
        success, message = await merchant_system.buy_item(
            sample_character, "blacksmith_imre", "iron_sword", 1, session=db_session
        )

        assert success is False
        assert "don't have enough money" in message.lower()

        # Gold should be unchanged
        await db_session.refresh(sample_character)
        assert sample_character.gold == 50

    async def test_buy_out_of_stock(self, db_session, sample_character, item_templates):
        """Test buying more than available stock."""
        # Health potion has stock of 10
        success, message = await merchant_system.buy_item(
            sample_character, "merchant_imre", "health_potion", 20, session=db_session
        )

        assert success is False
        assert "stock" in message.lower()

    async def test_buy_nonexistent_item(self, db_session, sample_character, item_templates):
        """Test buying item merchant doesn't sell."""
        success, message = await merchant_system.buy_item(
            sample_character, "merchant_imre", "nonexistent_item", 1, session=db_session
        )

        assert success is False
        assert "doesn't sell" in message.lower()

    async def test_buy_unlimited_stock(self, db_session, sample_character, item_templates):
        """Test buying items with unlimited stock."""
        # Bread has unlimited stock (-1)
        success, message = await merchant_system.buy_item(
            sample_character, "merchant_imre", "bread", 100, session=db_session
        )

        assert success is True

        # Check large quantity was created
        result = await db_session.execute(
            select(ItemInstance)
            .where(ItemInstance.owner_id == sample_character.id)
            .where(ItemInstance.template_id == "bread")
        )
        item = result.scalar_one_or_none()
        assert item is not None
        assert item.quantity == 100


@pytest.mark.asyncio
class TestSellingItems:
    """Test selling items to merchants."""

    async def test_sell_single_item(self, db_session, sample_character, item_templates):
        """Test selling a single item."""
        # First, give character an item to sell
        item = ItemInstance(
            template_id="bread",
            owner_id=sample_character.id,
            room_id=None,
            quantity=1,
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)

        initial_gold = sample_character.gold

        # Sell the item (bread value 5, sell price is 50% = 2 gold)
        success, message = await merchant_system.sell_item(
            sample_character, "merchant_imre", str(item.id), 1, session=db_session
        )

        assert success is True
        assert "sold" in message.lower()

        # Refresh character
        await db_session.refresh(sample_character)

        # Check gold was added (50% of 5 = 2 gold)
        assert sample_character.gold == initial_gold + 2

        # Check item was removed
        result = await db_session.execute(select(ItemInstance).where(ItemInstance.id == item.id))
        deleted_item = result.scalar_one_or_none()
        assert deleted_item is None

    async def test_sell_multiple_items(self, db_session, sample_character, item_templates):
        """Test selling multiple items from a stack."""
        # Give character a stack of items
        item = ItemInstance(
            template_id="bread",
            owner_id=sample_character.id,
            room_id=None,
            quantity=5,
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)

        initial_gold = sample_character.gold

        # Sell 3 of them
        success, message = await merchant_system.sell_item(
            sample_character, "merchant_imre", str(item.id), 3, session=db_session
        )

        assert success is True

        # Refresh character and item
        await db_session.refresh(sample_character)
        await db_session.refresh(item)

        # Check gold was added (3 bread at 2 gold each = 6 gold)
        assert sample_character.gold == initial_gold + 6

        # Check stack was reduced
        assert item.quantity == 2

    async def test_sell_quest_item(self, db_session, sample_character, item_templates):
        """Test that quest items cannot be sold."""
        # Give character a quest item
        item = ItemInstance(
            template_id="quest_item",
            owner_id=sample_character.id,
            room_id=None,
            quantity=1,
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)

        # Try to sell it
        success, message = await merchant_system.sell_item(
            sample_character, "merchant_imre", str(item.id), 1, session=db_session
        )

        assert success is False
        assert "quest item" in message.lower()

    async def test_sell_item_not_owned(self, db_session, sample_character, item_templates):
        """Test selling item not owned by character."""
        # Create item owned by someone else
        other_char = Character(
            user_id=sample_character.user_id,
            name="OtherChar",
            background=CharacterBackground.SCHOLAR,
            current_room_id="university_main_gates",
            gold=100,
        )
        db_session.add(other_char)
        await db_session.commit()

        item = ItemInstance(
            template_id="bread",
            owner_id=other_char.id,
            room_id=None,
            quantity=1,
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)

        # Try to sell it with our character
        success, message = await merchant_system.sell_item(
            sample_character, "merchant_imre", str(item.id), 1, session=db_session
        )

        assert success is False
        assert "don't own" in message.lower()

    async def test_sell_insufficient_quantity(self, db_session, sample_character, item_templates):
        """Test selling more items than you have."""
        # Give character one item
        item = ItemInstance(
            template_id="bread",
            owner_id=sample_character.id,
            room_id=None,
            quantity=1,
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)

        # Try to sell 5
        success, message = await merchant_system.sell_item(
            sample_character, "merchant_imre", str(item.id), 5, session=db_session
        )

        assert success is False
        assert "only have" in message.lower()

    async def test_sell_merchant_insufficient_gold(
        self, db_session, sample_character, item_templates
    ):
        """Test selling when merchant doesn't have enough gold."""
        # Give character expensive item
        item = ItemInstance(
            template_id="iron_sword",
            owner_id=sample_character.id,
            room_id=None,
            quantity=1,
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)

        # Get a merchant with low gold
        merchant_inventory = await merchant_system.get_merchant_inventory("merchant_imre")
        original_gold = merchant_inventory.gold
        merchant_inventory.gold = 1  # Set very low gold

        # Try to sell expensive item (iron sword value 100, sell price 50)
        success, message = await merchant_system.sell_item(
            sample_character, "merchant_imre", str(item.id), 1, session=db_session
        )

        assert success is False
        assert "doesn't have enough money" in message.lower()

        # Restore merchant gold
        merchant_inventory.gold = original_gold


@pytest.mark.asyncio
class TestMerchantStockManagement:
    """Test merchant stock updates."""

    async def test_stock_decreases_on_purchase(self, db_session, sample_character, item_templates):
        """Test that merchant stock decreases when items are bought."""
        merchant_inventory = await merchant_system.get_merchant_inventory("merchant_imre")
        initial_stock = merchant_inventory.items.get("health_potion", 0)

        # Buy some health potions
        await merchant_system.buy_item(
            sample_character, "merchant_imre", "health_potion", 2, session=db_session
        )

        # Check stock decreased
        assert merchant_inventory.items["health_potion"] == initial_stock - 2

    async def test_unlimited_stock_unchanged(self, db_session, sample_character, item_templates):
        """Test that unlimited stock (-1) doesn't change."""
        merchant_inventory = await merchant_system.get_merchant_inventory("merchant_imre")

        # Bread has unlimited stock
        await merchant_system.buy_item(
            sample_character, "merchant_imre", "bread", 100, session=db_session
        )

        # Stock should still be -1
        assert merchant_inventory.items["bread"] == -1

    async def test_stock_increases_on_sale(self, db_session, sample_character, item_templates):
        """Test that merchant stock increases when items are sold."""
        # Give character an item
        item = ItemInstance(
            template_id="health_potion",
            owner_id=sample_character.id,
            room_id=None,
            quantity=3,
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)

        merchant_inventory = await merchant_system.get_merchant_inventory("merchant_imre")
        initial_stock = merchant_inventory.items.get("health_potion", 0)

        # Sell items to merchant
        await merchant_system.sell_item(
            sample_character, "merchant_imre", str(item.id), 3, session=db_session
        )

        # Check stock increased
        assert merchant_inventory.items["health_potion"] == initial_stock + 3
