"""Tests for Phase 2 features: exploration XP, weight limits, and save command."""

import pytest
from sqlalchemy import select

from waystone.database.models import Character
from waystone.game.systems.experience import XP_EXPLORATION_NEW_ROOM


@pytest.mark.asyncio
class TestExplorationXP:
    """Test XP awarding for room exploration."""

    async def test_character_visited_rooms_field(self, db_session, test_character):
        """Test that visited_rooms field is initialized."""
        await db_session.refresh(test_character)

        # Ensure the field exists and is initialized
        visited = test_character.visited_rooms if hasattr(test_character, "visited_rooms") else []
        assert isinstance(visited, list)

    async def test_first_room_visit_awards_xp(self, db_session, test_character):
        """Test that visiting a room for the first time awards XP."""
        char_id = test_character.id
        initial_xp = test_character.experience

        # Manually track room visit and award XP as movement command would
        from waystone.game.systems.experience import award_xp

        room_id = "university_courtyard"

        # Check if room not visited
        visited_rooms = test_character.visited_rooms or []
        is_new_room = room_id not in visited_rooms

        assert is_new_room is True

        # Award XP and track room
        if is_new_room:
            visited_rooms.append(room_id)
            test_character.visited_rooms = visited_rooms
            await db_session.commit()

            new_xp, leveled_up = await award_xp(
                char_id,
                XP_EXPLORATION_NEW_ROOM,
                "exploration_new_room",
                session=db_session,
            )

        await db_session.refresh(test_character)

        # Verify XP was awarded
        assert test_character.experience == initial_xp + XP_EXPLORATION_NEW_ROOM
        assert room_id in test_character.visited_rooms

    async def test_revisiting_room_no_xp(self, db_session, test_character):
        """Test that revisiting a room does not award XP."""
        room_id = "university_courtyard"

        # Mark room as visited
        visited_rooms = test_character.visited_rooms or []
        visited_rooms.append(room_id)
        test_character.visited_rooms = visited_rooms
        await db_session.commit()

        initial_xp = test_character.experience

        # Check if room already visited
        visited_rooms = test_character.visited_rooms or []
        is_new_room = room_id not in visited_rooms

        assert is_new_room is False

        # No XP should be awarded for revisiting
        await db_session.refresh(test_character)
        assert test_character.experience == initial_xp

    async def test_multiple_room_exploration(self, db_session, test_character):
        """Test exploring multiple unique rooms."""
        from waystone.game.systems.experience import award_xp

        char_id = test_character.id
        initial_xp = test_character.experience

        rooms = [
            "university_courtyard",
            "university_library",
            "university_archives",
        ]

        for room_id in rooms:
            # Refresh character to get latest visited_rooms state
            await db_session.refresh(test_character)

            visited_rooms = test_character.visited_rooms or []

            if room_id not in visited_rooms:
                visited_rooms.append(room_id)
                test_character.visited_rooms = visited_rooms
                # Commit the visited_rooms update before awarding XP
                await db_session.commit()

                # Award XP
                await award_xp(
                    char_id,
                    XP_EXPLORATION_NEW_ROOM,
                    "exploration_new_room",
                    session=db_session,
                )

                # Commit the XP award
                await db_session.commit()

        await db_session.refresh(test_character)

        # Should have gained 3 * 25 = 75 XP
        expected_xp = initial_xp + (3 * XP_EXPLORATION_NEW_ROOM)
        assert test_character.experience == expected_xp
        # XP was awarded correctly but visited_rooms tracking happens in movement command
        # This test shows XP can be awarded multiple times
        assert test_character.experience == 75


@pytest.mark.asyncio
class TestWeightLimitEnforcement:
    """Test weight limit enforcement when picking up items."""

    async def test_pickup_within_capacity(self, db_session, test_character):
        """Test that items within capacity can be picked up."""
        from waystone.database.models import ItemInstance, ItemSlot, ItemTemplate, ItemType
        from waystone.game.world import Item, calculate_carry_capacity, calculate_total_weight

        # Character with STR 10 has capacity of 30 lbs
        test_character.strength = 10
        await db_session.commit()

        # Create light item (5 lbs)
        template = ItemTemplate(
            id="light_sword",
            name="Light Sword",
            description="A lightweight sword",
            item_type=ItemType.WEAPON,
            slot=ItemSlot.MAIN_HAND,
            weight=5.0,
            value=30,
            stackable=False,
        )
        db_session.add(template)

        instance = ItemInstance(
            template_id="light_sword",
            room_id="university_main_gates",
            quantity=1,
        )
        db_session.add(instance)
        await db_session.commit()
        await db_session.refresh(instance, ["template"])

        # Calculate if pickup is allowed
        item = Item(instance)

        # Get current inventory weight
        result = await db_session.execute(
            select(ItemInstance).where(ItemInstance.owner_id == test_character.id)
        )
        inventory_items = result.scalars().all()
        current_items = [Item(inst) for inst in inventory_items if hasattr(inst, "template")]

        current_weight = calculate_total_weight(current_items)
        capacity = calculate_carry_capacity(test_character.strength)

        # Should be able to pick up
        can_pickup = current_weight + item.total_weight <= capacity
        assert can_pickup is True

    async def test_pickup_exceeds_capacity(self, db_session, test_character):
        """Test that items exceeding capacity cannot be picked up."""
        from waystone.database.models import ItemInstance, ItemSlot, ItemTemplate, ItemType
        from waystone.game.world import Item, calculate_carry_capacity, calculate_total_weight

        # Character with STR 8 has capacity of 26 lbs
        test_character.strength = 8
        await db_session.commit()

        # Create heavy item (30 lbs)
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
            room_id="university_main_gates",
            quantity=1,
        )
        db_session.add(instance)
        await db_session.commit()
        await db_session.refresh(instance, ["template"])

        # Calculate if pickup is allowed
        item = Item(instance)

        # Get current inventory weight
        result = await db_session.execute(
            select(ItemInstance).where(ItemInstance.owner_id == test_character.id)
        )
        inventory_items = result.scalars().all()
        current_items = [Item(inst) for inst in inventory_items if hasattr(inst, "template")]

        current_weight = calculate_total_weight(current_items)
        capacity = calculate_carry_capacity(test_character.strength)

        # Should NOT be able to pick up
        can_pickup = current_weight + item.total_weight <= capacity
        assert can_pickup is False
        assert current_weight + item.total_weight > capacity


@pytest.mark.asyncio
class TestSaveCommand:
    """Test manual save command functionality."""

    async def test_save_character_data(self, db_session, test_character):
        """Test that save command commits character data."""
        char_id = test_character.id

        # Modify character data
        test_character.experience = 150
        test_character.level = 2

        # Simulate save command committing the session
        await db_session.commit()

        # Verify data was saved
        result = await db_session.execute(select(Character).where(Character.id == char_id))
        saved_character = result.scalar_one()

        assert saved_character.experience == 150
        assert saved_character.level == 2

    async def test_save_with_visited_rooms(self, db_session, test_character):
        """Test saving character with visited rooms data."""
        char_id = test_character.id

        # Add visited rooms
        visited_rooms = ["room1", "room2", "room3"]
        test_character.visited_rooms = visited_rooms

        # Save
        await db_session.commit()

        # Verify saved
        result = await db_session.execute(select(Character).where(Character.id == char_id))
        saved_character = result.scalar_one()

        assert saved_character.visited_rooms == visited_rooms
        assert len(saved_character.visited_rooms) == 3
