"""Inventory and equipment commands for Waystone MUD."""

from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from waystone.database.engine import get_session
from waystone.database.models import Character, ItemInstance, ItemSlot
from waystone.game.world import Item, calculate_carry_capacity, calculate_total_weight
from waystone.network import colorize

from .base import Command, CommandContext

logger = structlog.get_logger(__name__)


class InventoryCommand(Command):
    """Display character inventory with weights."""

    name = "inventory"
    aliases = ["i", "inv"]
    help_text = "inventory (i) - Show your inventory"
    min_args = 0

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the inventory command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
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

                # Get all items in inventory (not in rooms)
                inventory_items = [
                    Item(item_instance)
                    for item_instance in character.items
                    if item_instance.room_id is None
                ]

                # Calculate weights
                total_weight = calculate_total_weight(inventory_items)
                capacity = calculate_carry_capacity(character.strength)
                weight_percent = (total_weight / capacity * 100) if capacity > 0 else 0

                # Display header
                await ctx.connection.send_line("")
                await ctx.connection.send_line(colorize("=== Inventory ===", "CYAN"))
                await ctx.connection.send_line("")

                if not inventory_items:
                    await ctx.connection.send_line(colorize("You aren't carrying anything.", "DIM"))
                else:
                    # Display items
                    for item in sorted(inventory_items, key=lambda x: x.name):
                        await ctx.connection.send_line(
                            f"  {colorize(item.format_short_description(), 'WHITE')}"
                        )

                # Display weight summary
                await ctx.connection.send_line("")
                weight_color = (
                    "GREEN" if weight_percent < 75 else "YELLOW" if weight_percent < 100 else "RED"
                )
                await ctx.connection.send_line(
                    f"Carrying: {colorize(f'{total_weight:.1f}', weight_color)} / "
                    f"{capacity:.1f} lbs ({weight_percent:.0f}%)"
                )

                logger.debug(
                    "inventory_displayed",
                    character_id=ctx.session.character_id,
                    item_count=len(inventory_items),
                    total_weight=total_weight,
                )

        except Exception as e:
            logger.error("inventory_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Failed to display inventory. Please try again.", "RED")
            )


class GetCommand(Command):
    """Pick up an item from the current room."""

    name = "get"
    aliases = ["take", "pickup", "g"]
    help_text = "get <item> - Pick up an item from the room"
    min_args = 1

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the get command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        item_name = " ".join(ctx.args).lower()

        try:
            async with get_session() as session:
                # Get character
                result = await session.execute(
                    select(Character)
                    .where(Character.id == UUID(ctx.session.character_id))
                    .options(joinedload(Character.items).joinedload(ItemInstance.template))
                )
                character = result.scalar_one_or_none()

                if not character:
                    await ctx.connection.send_line(colorize("Character not found.", "RED"))
                    return

                # Find items in current room
                room_result = await session.execute(
                    select(ItemInstance)
                    .where(ItemInstance.room_id == character.current_room_id)
                    .options(joinedload(ItemInstance.template))
                )
                room_items = room_result.scalars().all()

                # Find matching item
                target_item = None
                for item_instance in room_items:
                    if item_name in item_instance.template.name.lower():
                        target_item = item_instance
                        break

                if not target_item:
                    await ctx.connection.send_line(
                        colorize(f"You don't see '{item_name}' here.", "YELLOW")
                    )
                    return

                # Create Item wrapper
                item = Item(target_item)

                # Check weight capacity
                inventory_items = [
                    Item(item_instance)
                    for item_instance in character.items
                    if item_instance.room_id is None
                ]
                current_weight = calculate_total_weight(inventory_items)
                capacity = calculate_carry_capacity(character.strength)

                if current_weight + item.total_weight > capacity:
                    await ctx.connection.send_line(
                        colorize(
                            f"You can't carry that much weight! "
                            f"({current_weight + item.total_weight:.1f} / {capacity:.1f} lbs)",
                            "RED",
                        )
                    )
                    return

                # Transfer item to character
                target_item.room_id = None
                target_item.owner_id = UUID(ctx.session.character_id)
                await session.commit()

                # Notify player
                await ctx.connection.send_line(colorize(f"You pick up {item.name}.", "GREEN"))

                # Notify room
                ctx.engine.broadcast_to_room(
                    character.current_room_id,
                    colorize(f"{character.name} picks up {item.name}.", "CYAN"),
                    exclude=ctx.session.id,
                )

                logger.info(
                    "item_picked_up",
                    character_id=ctx.session.character_id,
                    character_name=character.name,
                    item_id=str(item.id),
                    item_name=item.name,
                )

        except Exception as e:
            logger.error("get_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Failed to pick up item. Please try again.", "RED")
            )


class DropCommand(Command):
    """Drop an item to the current room."""

    name = "drop"
    aliases = ["dr"]
    help_text = "drop <item> - Drop an item to the room"
    min_args = 1

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the drop command."""
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

                # Find matching item in inventory
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

                # Create Item wrapper
                item = Item(target_item)

                # Check if item is equipped
                equipped_items = character.equipped or {}
                is_equipped = str(item.id) in equipped_items.values()

                if is_equipped:
                    await ctx.connection.send_line(
                        colorize(f"You must unequip {item.name} before dropping it.", "YELLOW")
                    )
                    return

                # Transfer item to room
                target_item.owner_id = None
                target_item.room_id = character.current_room_id
                await session.commit()

                # Notify player
                await ctx.connection.send_line(colorize(f"You drop {item.name}.", "GREEN"))

                # Notify room
                ctx.engine.broadcast_to_room(
                    character.current_room_id,
                    colorize(f"{character.name} drops {item.name}.", "CYAN"),
                    exclude=ctx.session.id,
                )

                logger.info(
                    "item_dropped",
                    character_id=ctx.session.character_id,
                    character_name=character.name,
                    item_id=str(item.id),
                    item_name=item.name,
                )

        except Exception as e:
            logger.error("drop_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Failed to drop item. Please try again.", "RED")
            )


class ExamineCommand(Command):
    """View detailed information about an item."""

    name = "examine"
    aliases = ["ex", "inspect", "x"]
    help_text = "examine <item> - View detailed item information"
    min_args = 1

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the examine command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        target_name = " ".join(ctx.args).lower()

        try:
            async with get_session() as session:
                # Get character
                result = await session.execute(
                    select(Character)
                    .where(Character.id == UUID(ctx.session.character_id))
                    .options(joinedload(Character.items).joinedload(ItemInstance.template))
                )
                character = result.scalar_one_or_none()

                if not character:
                    await ctx.connection.send_line(colorize("Character not found.", "RED"))
                    return

            # First, check for NPCs in the room
            room_id = character.current_room_id
            room_npc_ids = ctx.engine.room_npcs.get(room_id, [])

            for npc_id in room_npc_ids:
                npc_template = ctx.engine.npc_templates.get(npc_id)
                if npc_template and target_name in npc_template.name.lower():
                    # Found an NPC - display NPC details
                    await ctx.connection.send_line("")
                    await ctx.connection.send_line(colorize(npc_template.name.title(), "CYAN"))
                    await ctx.connection.send_line("-" * len(npc_template.name))
                    await ctx.connection.send_line(npc_template.description.strip())
                    await ctx.connection.send_line("")

                    # Show behavior
                    behavior_colors = {
                        "aggressive": "RED",
                        "passive": "GREEN",
                        "merchant": "YELLOW",
                        "stationary": "CYAN",
                        "wander": "BLUE",
                    }
                    behavior_color = behavior_colors.get(npc_template.behavior, "WHITE")
                    await ctx.connection.send_line(
                        f"Behavior: {colorize(npc_template.behavior.capitalize(), behavior_color)}"
                    )

                    # Show level and health
                    await ctx.connection.send_line(
                        f"Level: {colorize(str(npc_template.level), 'WHITE')} | "
                        f"Health: {colorize(str(npc_template.max_hp), 'WHITE')} HP"
                    )

                    # Show dialogue availability
                    if npc_template.dialogue:
                        await ctx.connection.send_line("")
                        await ctx.connection.send_line(
                            colorize("This NPC appears willing to talk.", "CYAN")
                        )
                        if "greeting" in npc_template.dialogue:
                            await ctx.connection.send_line(
                                f'  "{npc_template.dialogue["greeting"]}"'
                            )

                    logger.debug(
                        "npc_examined",
                        character_id=ctx.session.character_id,
                        npc_id=npc_template.id,
                    )
                    return

            # No NPC found, search for items
            async with get_session() as session:
                # Search inventory first
                target_item = None
                for item_instance in character.items:
                    if (
                        item_instance.room_id is None
                        and target_name in item_instance.template.name.lower()
                    ):
                        target_item = item_instance
                        break

                # If not in inventory, search room
                if not target_item:
                    item_result = await session.execute(
                        select(ItemInstance)
                        .where(ItemInstance.room_id == character.current_room_id)
                        .options(joinedload(ItemInstance.template))
                    )
                    room_items = item_result.scalars().all()

                    for room_item in room_items:
                        if target_name in room_item.template.name.lower():
                            target_item = room_item
                            break

                if not target_item:
                    await ctx.connection.send_line(
                        colorize(f"You don't see '{target_name}' here.", "YELLOW")
                    )
                    return

                # Create Item wrapper and display details
                item = Item(target_item)

                await ctx.connection.send_line("")
                await ctx.connection.send_line(colorize("=== Item Details ===", "CYAN"))
                await ctx.connection.send_line("")
                await ctx.connection.send_line(item.format_long_description())

                logger.debug(
                    "item_examined",
                    character_id=ctx.session.character_id,
                    item_id=str(item.id),
                    item_name=item.name,
                )

        except Exception as e:
            logger.error("examine_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(colorize("Failed to examine. Please try again.", "RED"))


class GiveCommand(Command):
    """Give an item to another player in the same room."""

    name = "give"
    aliases = []
    help_text = "give <item> <player> - Give an item to another player"
    min_args = 2

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the give command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        # Parse arguments - last arg is player name, rest is item name
        target_player_name = ctx.args[-1].lower()
        item_name = " ".join(ctx.args[:-1]).lower()

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

                # Find target player in same room
                room = ctx.engine.world.get(character.current_room_id)
                if not room:
                    await ctx.connection.send_line(
                        colorize("Your current location doesn't exist!", "RED")
                    )
                    return

                # Get all characters in room
                result = await session.execute(
                    select(Character).where(Character.id.in_([UUID(pid) for pid in room.players]))
                )
                room_characters = result.scalars().all()

                # Find target character
                target_character = None
                for char in room_characters:
                    if (
                        char.id != UUID(ctx.session.character_id)
                        and target_player_name in char.name.lower()
                    ):
                        target_character = char
                        break

                if not target_character:
                    await ctx.connection.send_line(
                        colorize(f"You don't see '{target_player_name}' here.", "YELLOW")
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

                # Create Item wrapper
                item = Item(target_item)

                # Check if item is equipped
                equipped_items = character.equipped or {}
                is_equipped = str(item.id) in equipped_items.values()

                if is_equipped:
                    await ctx.connection.send_line(
                        colorize(f"You must unequip {item.name} before giving it away.", "YELLOW")
                    )
                    return

                # Check target's carry capacity
                target_inventory_result = await session.execute(
                    select(ItemInstance)
                    .where(ItemInstance.owner_id == target_character.id)
                    .where(ItemInstance.room_id.is_(None))
                    .options(joinedload(ItemInstance.template))
                )
                target_inventory = [
                    Item(item_instance) for item_instance in target_inventory_result.scalars().all()
                ]

                target_weight = calculate_total_weight(target_inventory)
                target_capacity = calculate_carry_capacity(target_character.strength)

                if target_weight + item.total_weight > target_capacity:
                    await ctx.connection.send_line(
                        colorize(f"{target_character.name} can't carry that much weight!", "YELLOW")
                    )
                    return

                # Transfer item
                target_item.owner_id = target_character.id
                await session.commit()

                # Notify giver
                await ctx.connection.send_line(
                    colorize(f"You give {item.name} to {target_character.name}.", "GREEN")
                )

                # Notify receiver
                target_session = ctx.engine.character_to_session.get(str(target_character.id))
                if target_session:
                    await target_session.connection.send_line(
                        colorize(f"{character.name} gives you {item.name}.", "GREEN")
                    )

                # Notify room
                ctx.engine.broadcast_to_room(
                    character.current_room_id,
                    colorize(
                        f"{character.name} gives {item.name} to {target_character.name}.", "CYAN"
                    ),
                    exclude=ctx.session.id,
                )

                logger.info(
                    "item_given",
                    giver_id=ctx.session.character_id,
                    giver_name=character.name,
                    receiver_id=str(target_character.id),
                    receiver_name=target_character.name,
                    item_id=str(item.id),
                    item_name=item.name,
                )

        except Exception as e:
            logger.error("give_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Failed to give item. Please try again.", "RED")
            )


class EquipCommand(Command):
    """Equip an item from inventory."""

    name = "equip"
    aliases = ["wear", "wield"]
    help_text = "equip <item> - Equip an item from your inventory"
    min_args = 1

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the equip command."""
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

                # Find matching item in inventory
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

                # Create Item wrapper
                item = Item(target_item)

                # Check if item is equippable
                if not item.is_equippable:
                    await ctx.connection.send_line(
                        colorize(f"You can't equip {item.name}.", "YELLOW")
                    )
                    return

                # Check if slot is already occupied
                equipped_items = character.equipped or {}
                slot_name = item.slot.value

                if slot_name in equipped_items:
                    # Get currently equipped item
                    current_item_id = equipped_items[slot_name]
                    current_instance = await session.get(ItemInstance, UUID(current_item_id))
                    if current_instance:
                        current_item = Item(current_instance)
                        await ctx.connection.send_line(
                            colorize(f"You must unequip {current_item.name} first.", "YELLOW")
                        )
                        return

                # Equip item
                equipped_items[slot_name] = str(item.id)
                character.equipped = equipped_items
                await session.commit()

                # Notify player
                await ctx.connection.send_line(colorize(f"You equip {item.name}.", "GREEN"))

                # Notify room
                ctx.engine.broadcast_to_room(
                    character.current_room_id,
                    colorize(f"{character.name} equips {item.name}.", "CYAN"),
                    exclude=ctx.session.id,
                )

                logger.info(
                    "item_equipped",
                    character_id=ctx.session.character_id,
                    character_name=character.name,
                    item_id=str(item.id),
                    item_name=item.name,
                    slot=slot_name,
                )

        except Exception as e:
            logger.error("equip_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Failed to equip item. Please try again.", "RED")
            )


class UnequipCommand(Command):
    """Unequip an item from an equipment slot."""

    name = "unequip"
    aliases = ["remove", "unwield"]
    help_text = "unequip <slot> - Unequip an item from a slot (e.g., 'main_hand', 'body')"
    min_args = 1

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the unequip command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(colorize("You must be playing a character.", "RED"))
            return

        slot_input = "_".join(ctx.args).lower()

        # Validate slot
        try:
            slot = ItemSlot(slot_input)
        except ValueError:
            await ctx.connection.send_line(
                colorize(
                    f"Invalid slot '{slot_input}'. Valid slots: head, body, hands, legs, "
                    f"feet, main_hand, off_hand, accessory",
                    "YELLOW",
                )
            )
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

                # Check if slot has an item
                equipped_items = character.equipped or {}
                slot_name = slot.value

                if slot_name not in equipped_items:
                    await ctx.connection.send_line(
                        colorize(
                            f"You don't have anything equipped in your {slot_name.replace('_', ' ')}.",
                            "YELLOW",
                        )
                    )
                    return

                # Get the equipped item
                item_id = equipped_items[slot_name]
                item_instance = await session.get(
                    ItemInstance, UUID(item_id), options=[joinedload(ItemInstance.template)]
                )

                if not item_instance:
                    # Item no longer exists, clean up
                    del equipped_items[slot_name]
                    character.equipped = equipped_items
                    await session.commit()
                    await ctx.connection.send_line(colorize("That item no longer exists.", "RED"))
                    return

                item = Item(item_instance)

                # Unequip item
                del equipped_items[slot_name]
                character.equipped = equipped_items
                await session.commit()

                # Notify player
                await ctx.connection.send_line(colorize(f"You unequip {item.name}.", "GREEN"))

                # Notify room
                ctx.engine.broadcast_to_room(
                    character.current_room_id,
                    colorize(f"{character.name} unequips {item.name}.", "CYAN"),
                    exclude=ctx.session.id,
                )

                logger.info(
                    "item_unequipped",
                    character_id=ctx.session.character_id,
                    character_name=character.name,
                    item_id=str(item.id),
                    item_name=item.name,
                    slot=slot_name,
                )

        except Exception as e:
            logger.error("unequip_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Failed to unequip item. Please try again.", "RED")
            )


class EquipmentCommand(Command):
    """Display currently equipped items."""

    name = "equipment"
    aliases = ["eq", "equipped"]
    help_text = "equipment (eq) - Show your equipped items"
    min_args = 0

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the equipment command."""
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

                # Display header
                await ctx.connection.send_line("")
                await ctx.connection.send_line(colorize("=== Equipment ===", "CYAN"))
                await ctx.connection.send_line("")

                equipped_items = character.equipped or {}

                if not equipped_items:
                    await ctx.connection.send_line(
                        colorize("You don't have anything equipped.", "DIM")
                    )
                    return

                # Display each equipment slot
                all_slots = [
                    ItemSlot.HEAD,
                    ItemSlot.BODY,
                    ItemSlot.HANDS,
                    ItemSlot.LEGS,
                    ItemSlot.FEET,
                    ItemSlot.MAIN_HAND,
                    ItemSlot.OFF_HAND,
                    ItemSlot.ACCESSORY,
                ]

                for slot in all_slots:
                    slot_name = slot.value
                    display_name = slot_name.replace("_", " ").title()

                    if slot_name in equipped_items:
                        # Get item details
                        item_id = equipped_items[slot_name]
                        item_instance = await session.get(
                            ItemInstance, UUID(item_id), options=[joinedload(ItemInstance.template)]
                        )

                        if item_instance:
                            item = Item(item_instance)
                            await ctx.connection.send_line(
                                f"  {colorize(display_name + ':', 'YELLOW')} {item.name}"
                            )
                        else:
                            await ctx.connection.send_line(
                                f"  {colorize(display_name + ':', 'DIM')} <empty>"
                            )
                    else:
                        await ctx.connection.send_line(
                            f"  {colorize(display_name + ':', 'DIM')} <empty>"
                        )

                logger.debug(
                    "equipment_displayed",
                    character_id=ctx.session.character_id,
                    equipped_count=len(equipped_items),
                )

        except Exception as e:
            logger.error("equipment_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Failed to display equipment. Please try again.", "RED")
            )
