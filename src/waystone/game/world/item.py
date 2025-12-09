"""Item game logic for Waystone MUD inventory and equipment system."""

from typing import Any
from uuid import UUID

from waystone.database.models import ItemInstance, ItemSlot, ItemType


class Item:
    """
    Game logic wrapper for item instances.

    Provides utility methods for working with items in the game world,
    combining template data with instance-specific information.
    """

    def __init__(self, instance: ItemInstance) -> None:
        """
        Initialize Item from database instance.

        Args:
            instance: ItemInstance database model with loaded template
        """
        self.instance = instance
        self.template = instance.template

    @property
    def id(self) -> UUID:
        """Get item instance ID."""
        return self.instance.id

    @property
    def template_id(self) -> str:
        """Get item template ID."""
        return self.instance.template_id

    @property
    def name(self) -> str:
        """Get item name from template."""
        return self.template.name

    @property
    def description(self) -> str:
        """Get item description from template."""
        return self.template.description

    @property
    def item_type(self) -> ItemType:
        """Get item type from template."""
        return self.template.item_type

    @property
    def slot(self) -> ItemSlot:
        """Get equipment slot from template."""
        return self.template.slot

    @property
    def weight(self) -> float:
        """Get item weight from template."""
        return self.template.weight

    @property
    def value(self) -> int:
        """Get item value from template."""
        return self.template.value

    @property
    def quantity(self) -> int:
        """Get item quantity."""
        return self.instance.quantity

    @property
    def stackable(self) -> bool:
        """Check if item is stackable from template."""
        return self.template.stackable

    @property
    def unique(self) -> bool:
        """Check if item is unique from template."""
        return self.template.unique

    @property
    def quest_item(self) -> bool:
        """Check if item is a quest item from template."""
        return self.template.quest_item

    @property
    def total_weight(self) -> float:
        """Calculate total weight including quantity."""
        return self.weight * self.quantity

    @property
    def is_equippable(self) -> bool:
        """Check if item can be equipped."""
        return self.slot != ItemSlot.NONE

    @property
    def is_weapon(self) -> bool:
        """Check if item is a weapon."""
        return self.item_type == ItemType.WEAPON

    @property
    def is_armor(self) -> bool:
        """Check if item is armor."""
        return self.item_type == ItemType.ARMOR

    @property
    def is_consumable(self) -> bool:
        """Check if item is consumable."""
        return self.item_type == ItemType.CONSUMABLE

    def get_property(self, key: str, default: Any = None) -> Any:
        """
        Get a property from template properties.

        Args:
            key: Property key to retrieve
            default: Default value if property not found

        Returns:
            Property value or default
        """
        if self.template.properties:
            return self.template.properties.get(key, default)
        return default

    def get_instance_property(self, key: str, default: Any = None) -> Any:
        """
        Get a property from instance properties.

        Args:
            key: Property key to retrieve
            default: Default value if property not found

        Returns:
            Property value or default
        """
        if self.instance.instance_properties:
            return self.instance.instance_properties.get(key, default)
        return default

    def format_short_description(self) -> str:
        """
        Format a short description for inventory listing.

        Returns:
            Formatted string like "Iron Sword (3.0 lbs)" or "Health Potion x5 (2.5 lbs)"
        """
        if self.stackable and self.quantity > 1:
            return f"{self.name} x{self.quantity} ({self.total_weight:.1f} lbs)"
        return f"{self.name} ({self.weight:.1f} lbs)"

    def format_long_description(self) -> str:
        """
        Format a detailed description for examination.

        Returns:
            Multi-line formatted description with all item details
        """
        lines = [
            f"Name: {self.name}",
            f"Type: {self.item_type.value.capitalize()}",
            f"Weight: {self.weight:.1f} lbs",
            f"Value: {self.value} coins",
        ]

        if self.stackable:
            lines.append(f"Quantity: {self.quantity}")

        if self.is_equippable:
            lines.append(f"Slot: {self.slot.value.replace('_', ' ').title()}")

        # Add damage for weapons
        damage = self.get_property("damage")
        if damage:
            lines.append(f"Damage: {damage}")

        # Add armor for armor pieces
        armor = self.get_property("armor")
        if armor:
            lines.append(f"Armor: {armor}")

        # Add effect for consumables
        effect = self.get_property("effect")
        if effect:
            lines.append(f"Effect: {effect}")

        # Add description
        lines.append("")
        lines.append(self.description)

        # Add flags
        flags = []
        if self.stackable:
            flags.append("Stackable")
        if self.unique:
            flags.append("Unique")
        if self.quest_item:
            flags.append("Quest Item")

        if flags:
            lines.append("")
            lines.append(f"Flags: {', '.join(flags)}")

        return "\n".join(lines)

    def can_stack_with(self, other: "Item") -> bool:
        """
        Check if this item can stack with another item.

        Args:
            other: Other item to check stacking compatibility

        Returns:
            True if items can stack together
        """
        return self.stackable and other.stackable and self.template_id == other.template_id

    def __repr__(self) -> str:
        """String representation of Item."""
        return (
            f"<Item(id={self.id}, template='{self.template_id}', "
            f"name='{self.name}', quantity={self.quantity})>"
        )


def calculate_carry_capacity(strength: int) -> float:
    """
    Calculate character carry capacity based on strength.

    Args:
        strength: Character's strength attribute

    Returns:
        Carry capacity in pounds
    """
    return 10.0 + (strength * 2.0)


def calculate_total_weight(items: list[Item]) -> float:
    """
    Calculate total weight of a list of items.

    Args:
        items: List of Item objects

    Returns:
        Total weight in pounds
    """
    return sum(item.total_weight for item in items)
