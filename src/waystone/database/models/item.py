"""Item models for Waystone MUD inventory and equipment system."""

import enum
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Enum, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .character import Character


class ItemType(enum.Enum):
    """Types of items available in the game."""

    WEAPON = "weapon"
    ARMOR = "armor"
    CONSUMABLE = "consumable"
    QUEST = "quest"
    MISC = "misc"


class ItemSlot(enum.Enum):
    """Equipment slots where items can be worn."""

    HEAD = "head"
    BODY = "body"
    HANDS = "hands"
    LEGS = "legs"
    FEET = "feet"
    MAIN_HAND = "main_hand"
    OFF_HAND = "off_hand"
    ACCESSORY = "accessory"
    NONE = "none"  # For non-equippable items


class ItemTemplate(Base, TimestampMixin):
    """
    Item template defining the archetype for items.

    Templates are used to create item instances in the world.
    They define the static properties of items like name, description, and base stats.
    """

    __tablename__ = "item_templates"

    id: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
        comment="Unique item template identifier (e.g., 'iron_sword')",
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Display name of the item",
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Detailed description of the item",
    )

    item_type: Mapped[ItemType] = mapped_column(
        Enum(ItemType),
        nullable=False,
        comment="Type of item (weapon, armor, consumable, etc.)",
    )

    slot: Mapped[ItemSlot] = mapped_column(
        Enum(ItemSlot),
        nullable=False,
        default=ItemSlot.NONE,
        server_default=ItemSlot.NONE.value,
        comment="Equipment slot where this item can be worn",
    )

    weight: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        server_default="0.0",
        comment="Weight of the item in pounds",
    )

    value: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Base value of the item in currency",
    )

    stackable: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        server_default="false",
        comment="Whether this item can be stacked",
    )

    unique: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        server_default="false",
        comment="Whether this is a unique item (only one can exist)",
    )

    quest_item: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        server_default="false",
        comment="Whether this is a quest item",
    )

    # Item-specific properties stored as JSON-like data
    # Examples: {"damage": "1d8", "armor": 2, "effect": "heal:20"}
    properties: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        default=None,
        comment="Additional item properties (damage, armor, effects, etc.)",
    )

    def __repr__(self) -> str:
        """String representation of ItemTemplate."""
        return (
            f"<ItemTemplate(id='{self.id}', name='{self.name}', "
            f"type={self.item_type.value}, slot={self.slot.value})>"
        )


class ItemInstance(Base, TimestampMixin):
    """
    Individual item instance in the game world.

    Represents an actual item that exists, either in a character's inventory,
    equipped on a character, or lying in a room.
    """

    __tablename__ = "item_instances"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique item instance identifier",
    )

    template_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("item_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Foreign key to item template",
    )

    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Foreign key to owning character (null if in room)",
    )

    room_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="Room identifier where item is located (null if in inventory)",
    )

    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
        comment="Quantity for stackable items",
    )

    # Custom properties for this specific instance (e.g., durability, enchantments)
    instance_properties: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        default=None,
        comment="Instance-specific properties (durability, enchantments, etc.)",
    )

    # Relationships
    template: Mapped["ItemTemplate"] = relationship(
        "ItemTemplate",
        lazy="joined",
    )

    owner: Mapped["Character | None"] = relationship(
        "Character",
        back_populates="items",
        foreign_keys=[owner_id],
    )

    def __repr__(self) -> str:
        """String representation of ItemInstance."""
        location = f"owner={self.owner_id}" if self.owner_id else f"room={self.room_id}"
        return (
            f"<ItemInstance(id={self.id}, template='{self.template_id}', "
            f"{location}, quantity={self.quantity})>"
        )
