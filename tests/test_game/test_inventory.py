"""Tests for inventory and equipment system."""

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
from waystone.game.world import Item, calculate_carry_capacity, calculate_total_weight


@pytest.mark.asyncio
class TestItemTemplate:
    """Test ItemTemplate model."""

    async def test_create_item_template(self, db_session):
        """Test creating an item template."""
        template = ItemTemplate(
            id="iron_sword",
            name="Iron Sword",
            description="A simple iron sword",
            item_type=ItemType.WEAPON,
            slot=ItemSlot.MAIN_HAND,
            weight=3.0,
            value=50,
            stackable=False,
            unique=False,
            quest_item=False,
            properties={"damage": "1d8"},
        )

        db_session.add(template)
        await db_session.commit()

        result = await db_session.execute(
            select(ItemTemplate).where(ItemTemplate.id == "iron_sword")
        )
        saved_template = result.scalar_one()

        assert saved_template.name == "Iron Sword"
        assert saved_template.item_type == ItemType.WEAPON
        assert saved_template.slot == ItemSlot.MAIN_HAND
        assert saved_template.weight == 3.0
        assert saved_template.value == 50
        assert saved_template.properties["damage"] == "1d8"

    async def test_stackable_item_template(self, db_session):
        """Test creating a stackable item template."""
        template = ItemTemplate(
            id="health_potion",
            name="Health Potion",
            description="Restores health",
            item_type=ItemType.CONSUMABLE,
            slot=ItemSlot.NONE,
            weight=0.5,
            value=10,
            stackable=True,
            unique=False,
            quest_item=False,
            properties={"effect": "heal:20"},
        )

        db_session.add(template)
        await db_session.commit()

        result = await db_session.execute(
            select(ItemTemplate).where(ItemTemplate.id == "health_potion")
        )
        saved_template = result.scalar_one()

        assert saved_template.stackable is True
        assert saved_template.item_type == ItemType.CONSUMABLE


@pytest.mark.asyncio
class TestItemInstance:
    """Test ItemInstance model."""

    async def test_create_item_instance(self, db_session, test_user, test_character):
        """Test creating an item instance."""
        # Create template
        template = ItemTemplate(
            id="iron_sword",
            name="Iron Sword",
            description="A simple iron sword",
            item_type=ItemType.WEAPON,
            slot=ItemSlot.MAIN_HAND,
            weight=3.0,
            value=50,
            stackable=False,
            unique=False,
            quest_item=False,
        )
        db_session.add(template)

        # Create instance
        instance = ItemInstance(
            template_id="iron_sword",
            owner_id=test_character.id,
            room_id=None,
            quantity=1,
        )
        db_session.add(instance)
        await db_session.commit()

        # Verify
        result = await db_session.execute(
            select(ItemInstance).where(ItemInstance.owner_id == test_character.id)
        )
        saved_instance = result.scalar_one()

        assert saved_instance.template_id == "iron_sword"
        assert saved_instance.owner_id == test_character.id
        assert saved_instance.room_id is None
        assert saved_instance.quantity == 1

    async def test_item_in_room(self, db_session):
        """Test creating an item instance in a room."""
        # Create template
        template = ItemTemplate(
            id="health_potion",
            name="Health Potion",
            description="Restores health",
            item_type=ItemType.CONSUMABLE,
            slot=ItemSlot.NONE,
            weight=0.5,
            value=10,
            stackable=True,
        )
        db_session.add(template)

        # Create instance in room
        instance = ItemInstance(
            template_id="health_potion",
            owner_id=None,
            room_id="university_main_gates",
            quantity=3,
        )
        db_session.add(instance)
        await db_session.commit()

        # Verify
        result = await db_session.execute(
            select(ItemInstance).where(ItemInstance.room_id == "university_main_gates")
        )
        saved_instance = result.scalar_one()

        assert saved_instance.owner_id is None
        assert saved_instance.room_id == "university_main_gates"
        assert saved_instance.quantity == 3


@pytest.mark.asyncio
class TestItemClass:
    """Test Item game logic wrapper."""

    async def test_item_properties(self, db_session):
        """Test Item wrapper properties."""
        # Create template and instance
        template = ItemTemplate(
            id="iron_sword",
            name="Iron Sword",
            description="A simple iron sword",
            item_type=ItemType.WEAPON,
            slot=ItemSlot.MAIN_HAND,
            weight=3.0,
            value=50,
            stackable=False,
            unique=False,
            quest_item=False,
            properties={"damage": "1d8"},
        )
        db_session.add(template)

        instance = ItemInstance(
            template_id="iron_sword",
            quantity=1,
        )
        db_session.add(instance)
        await db_session.commit()

        # Refresh to load template relationship
        await db_session.refresh(instance, ["template"])

        # Create Item wrapper
        item = Item(instance)

        assert item.name == "Iron Sword"
        assert item.description == "A simple iron sword"
        assert item.item_type == ItemType.WEAPON
        assert item.slot == ItemSlot.MAIN_HAND
        assert item.weight == 3.0
        assert item.value == 50
        assert item.quantity == 1
        assert item.total_weight == 3.0
        assert item.is_equippable is True
        assert item.is_weapon is True
        assert item.is_armor is False
        assert item.stackable is False
        assert item.get_property("damage") == "1d8"

    async def test_stackable_item(self, db_session):
        """Test stackable item properties."""
        template = ItemTemplate(
            id="health_potion",
            name="Health Potion",
            description="Restores health",
            item_type=ItemType.CONSUMABLE,
            slot=ItemSlot.NONE,
            weight=0.5,
            value=10,
            stackable=True,
        )
        db_session.add(template)

        instance = ItemInstance(
            template_id="health_potion",
            quantity=5,
        )
        db_session.add(instance)
        await db_session.commit()
        await db_session.refresh(instance, ["template"])

        item = Item(instance)

        assert item.quantity == 5
        assert item.weight == 0.5
        assert item.total_weight == 2.5  # 5 * 0.5
        assert item.stackable is True
        assert item.is_equippable is False
        assert item.is_consumable is True

    async def test_item_can_stack_with(self, db_session):
        """Test item stacking compatibility."""
        template = ItemTemplate(
            id="health_potion",
            name="Health Potion",
            description="Restores health",
            item_type=ItemType.CONSUMABLE,
            slot=ItemSlot.NONE,
            weight=0.5,
            value=10,
            stackable=True,
        )
        db_session.add(template)

        instance1 = ItemInstance(template_id="health_potion", quantity=3)
        instance2 = ItemInstance(template_id="health_potion", quantity=2)
        db_session.add_all([instance1, instance2])
        await db_session.commit()
        await db_session.refresh(instance1, ["template"])
        await db_session.refresh(instance2, ["template"])

        item1 = Item(instance1)
        item2 = Item(instance2)

        assert item1.can_stack_with(item2) is True

    async def test_item_format_short_description(self, db_session):
        """Test item short description formatting."""
        template = ItemTemplate(
            id="health_potion",
            name="Health Potion",
            description="Restores health",
            item_type=ItemType.CONSUMABLE,
            slot=ItemSlot.NONE,
            weight=0.5,
            value=10,
            stackable=True,
        )
        db_session.add(template)

        instance = ItemInstance(template_id="health_potion", quantity=5)
        db_session.add(instance)
        await db_session.commit()
        await db_session.refresh(instance, ["template"])

        item = Item(instance)
        desc = item.format_short_description()

        assert "Health Potion" in desc
        assert "x5" in desc
        assert "2.5 lbs" in desc

    async def test_item_format_long_description(self, db_session):
        """Test item long description formatting."""
        template = ItemTemplate(
            id="iron_sword",
            name="Iron Sword",
            description="A simple iron sword",
            item_type=ItemType.WEAPON,
            slot=ItemSlot.MAIN_HAND,
            weight=3.0,
            value=50,
            stackable=False,
            unique=False,
            quest_item=False,
            properties={"damage": "1d8"},
        )
        db_session.add(template)

        instance = ItemInstance(template_id="iron_sword", quantity=1)
        db_session.add(instance)
        await db_session.commit()
        await db_session.refresh(instance, ["template"])

        item = Item(instance)
        desc = item.format_long_description()

        assert "Name: Iron Sword" in desc
        assert "Type: Weapon" in desc
        assert "Weight: 3.0 lbs" in desc
        assert "Damage: 1d8" in desc
        assert "A simple iron sword" in desc


class TestCarryCapacity:
    """Test carry capacity calculations."""

    def test_base_carry_capacity(self):
        """Test carry capacity with base strength."""
        capacity = calculate_carry_capacity(10)
        assert capacity == 30.0  # 10 + (10 * 2)

    def test_low_strength_capacity(self):
        """Test carry capacity with low strength."""
        capacity = calculate_carry_capacity(8)
        assert capacity == 26.0  # 10 + (8 * 2)

    def test_high_strength_capacity(self):
        """Test carry capacity with high strength."""
        capacity = calculate_carry_capacity(18)
        assert capacity == 46.0  # 10 + (18 * 2)


class TestWeightCalculations:
    """Test weight calculation functions."""

    async def test_calculate_total_weight_empty(self):
        """Test calculating total weight of empty list."""
        total = calculate_total_weight([])
        assert total == 0.0

    async def test_calculate_total_weight_single_item(self, db_session):
        """Test calculating total weight of single item."""
        template = ItemTemplate(
            id="iron_sword",
            name="Iron Sword",
            description="A simple iron sword",
            item_type=ItemType.WEAPON,
            slot=ItemSlot.MAIN_HAND,
            weight=3.0,
            value=50,
            stackable=False,
        )
        db_session.add(template)

        instance = ItemInstance(template_id="iron_sword", quantity=1)
        db_session.add(instance)
        await db_session.commit()
        await db_session.refresh(instance, ["template"])

        items = [Item(instance)]
        total = calculate_total_weight(items)
        assert total == 3.0

    async def test_calculate_total_weight_multiple_items(self, db_session):
        """Test calculating total weight of multiple items."""
        template1 = ItemTemplate(
            id="iron_sword",
            name="Iron Sword",
            description="A simple iron sword",
            item_type=ItemType.WEAPON,
            slot=ItemSlot.MAIN_HAND,
            weight=3.0,
            value=50,
            stackable=False,
        )
        template2 = ItemTemplate(
            id="health_potion",
            name="Health Potion",
            description="Restores health",
            item_type=ItemType.CONSUMABLE,
            slot=ItemSlot.NONE,
            weight=0.5,
            value=10,
            stackable=True,
        )
        db_session.add_all([template1, template2])

        instance1 = ItemInstance(template_id="iron_sword", quantity=1)
        instance2 = ItemInstance(template_id="health_potion", quantity=5)
        db_session.add_all([instance1, instance2])
        await db_session.commit()
        await db_session.refresh(instance1, ["template"])
        await db_session.refresh(instance2, ["template"])

        items = [Item(instance1), Item(instance2)]
        total = calculate_total_weight(items)
        assert total == 5.5  # 3.0 + (0.5 * 5)


@pytest.mark.asyncio
class TestCharacterEquipment:
    """Test character equipment system."""

    async def test_character_equipped_field(self, db_session, test_user):
        """Test character equipped items field."""
        character = Character(
            user_id=test_user.id,
            name="TestChar",
            background=CharacterBackground.SCHOLAR,
            current_room_id="university_main_gates",
            equipped={},
        )
        db_session.add(character)
        await db_session.commit()

        assert character.equipped == {}

    async def test_equip_item(self, db_session, test_user):
        """Test equipping an item."""
        # Create character
        character = Character(
            user_id=test_user.id,
            name="TestChar",
            background=CharacterBackground.SCHOLAR,
            current_room_id="university_main_gates",
            equipped={},
        )
        db_session.add(character)

        # Create item
        template = ItemTemplate(
            id="iron_sword",
            name="Iron Sword",
            description="A simple iron sword",
            item_type=ItemType.WEAPON,
            slot=ItemSlot.MAIN_HAND,
            weight=3.0,
            value=50,
            stackable=False,
        )
        db_session.add(template)

        instance = ItemInstance(
            template_id="iron_sword",
            owner_id=character.id,
            quantity=1,
        )
        db_session.add(instance)
        await db_session.commit()

        # Equip item
        character.equipped = {"main_hand": str(instance.id)}
        await db_session.commit()

        # Verify
        result = await db_session.execute(select(Character).where(Character.id == character.id))
        saved_char = result.scalar_one()

        assert "main_hand" in saved_char.equipped
        assert saved_char.equipped["main_hand"] == str(instance.id)

    async def test_multiple_equipped_items(self, db_session, test_user):
        """Test equipping multiple items."""
        # Create character
        character = Character(
            user_id=test_user.id,
            name="TestChar",
            background=CharacterBackground.SCHOLAR,
            current_room_id="university_main_gates",
            equipped={},
        )
        db_session.add(character)

        # Create items
        sword_template = ItemTemplate(
            id="iron_sword",
            name="Iron Sword",
            description="A simple iron sword",
            item_type=ItemType.WEAPON,
            slot=ItemSlot.MAIN_HAND,
            weight=3.0,
            value=50,
            stackable=False,
        )
        armor_template = ItemTemplate(
            id="leather_armor",
            name="Leather Armor",
            description="Basic leather armor",
            item_type=ItemType.ARMOR,
            slot=ItemSlot.BODY,
            weight=8.0,
            value=25,
            stackable=False,
        )
        db_session.add_all([sword_template, armor_template])

        sword_instance = ItemInstance(
            template_id="iron_sword",
            owner_id=character.id,
            quantity=1,
        )
        armor_instance = ItemInstance(
            template_id="leather_armor",
            owner_id=character.id,
            quantity=1,
        )
        db_session.add_all([sword_instance, armor_instance])
        await db_session.commit()

        # Equip both items
        character.equipped = {
            "main_hand": str(sword_instance.id),
            "body": str(armor_instance.id),
        }
        await db_session.commit()

        # Verify
        result = await db_session.execute(select(Character).where(Character.id == character.id))
        saved_char = result.scalar_one()

        assert len(saved_char.equipped) == 2
        assert "main_hand" in saved_char.equipped
        assert "body" in saved_char.equipped


@pytest.mark.asyncio
class TestInventoryCapacity:
    """Test inventory capacity limits."""

    async def test_weight_within_capacity(self, db_session, test_user):
        """Test character can carry items within capacity."""
        # Create character with STR 10 (capacity = 30 lbs)
        character = Character(
            user_id=test_user.id,
            name="TestChar",
            background=CharacterBackground.SCHOLAR,
            current_room_id="university_main_gates",
            strength=10,
        )
        db_session.add(character)

        # Create items totaling 20 lbs
        template = ItemTemplate(
            id="iron_sword",
            name="Iron Sword",
            description="A simple iron sword",
            item_type=ItemType.WEAPON,
            slot=ItemSlot.MAIN_HAND,
            weight=10.0,
            value=50,
            stackable=False,
        )
        db_session.add(template)

        instance1 = ItemInstance(
            template_id="iron_sword",
            owner_id=character.id,
            quantity=1,
        )
        instance2 = ItemInstance(
            template_id="iron_sword",
            owner_id=character.id,
            quantity=1,
        )
        db_session.add_all([instance1, instance2])
        await db_session.commit()
        await db_session.refresh(instance1, ["template"])
        await db_session.refresh(instance2, ["template"])

        # Calculate weights
        items = [Item(instance1), Item(instance2)]
        total_weight = calculate_total_weight(items)
        capacity = calculate_carry_capacity(character.strength)

        assert total_weight == 20.0
        assert capacity == 30.0
        assert total_weight <= capacity

    async def test_weight_over_capacity(self, db_session, test_user):
        """Test detecting over-capacity weight."""
        # Create character with STR 8 (capacity = 26 lbs)
        character = Character(
            user_id=test_user.id,
            name="TestChar",
            background=CharacterBackground.SCHOLAR,
            current_room_id="university_main_gates",
            strength=8,
        )
        db_session.add(character)

        # Create items totaling 30 lbs
        template = ItemTemplate(
            id="heavy_armor",
            name="Heavy Armor",
            description="Very heavy armor",
            item_type=ItemType.ARMOR,
            slot=ItemSlot.BODY,
            weight=30.0,
            value=100,
            stackable=False,
        )
        db_session.add(template)

        instance = ItemInstance(
            template_id="heavy_armor",
            owner_id=character.id,
            quantity=1,
        )
        db_session.add(instance)
        await db_session.commit()
        await db_session.refresh(instance, ["template"])

        # Calculate weights
        items = [Item(instance)]
        total_weight = calculate_total_weight(items)
        capacity = calculate_carry_capacity(character.strength)

        assert total_weight == 30.0
        assert capacity == 26.0
        assert total_weight > capacity
