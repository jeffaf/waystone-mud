"""Character model for Waystone MUD player characters."""

import enum
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Enum, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .item import ItemInstance
    from .quest import Quest
    from .user import User


class CharacterBackground(enum.Enum):
    """Available character backgrounds in the Kingkiller Chronicle universe."""

    SCHOLAR = "Scholar"
    MERCHANT = "Merchant"
    PERFORMER = "Performer"
    WAYFARER = "Wayfarer"
    NOBLE = "Noble"
    COMMONER = "Commoner"


class Character(Base, TimestampMixin):
    """Player character model with stats, background, and location."""

    __tablename__ = "characters"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique character identifier",
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Foreign key to owning user",
    )

    name: Mapped[str] = mapped_column(
        String(30),
        unique=True,
        nullable=False,
        index=True,
        comment="Unique character name (2-30 characters)",
    )

    background: Mapped[CharacterBackground] = mapped_column(
        Enum(CharacterBackground),
        nullable=False,
        comment="Character background/origin",
    )

    # Core attributes (D&D style)
    strength: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=10,
        server_default="10",
        comment="Physical strength attribute",
    )

    dexterity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=10,
        server_default="10",
        comment="Agility and reflexes attribute",
    )

    constitution: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=10,
        server_default="10",
        comment="Health and endurance attribute",
    )

    intelligence: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=10,
        server_default="10",
        comment="Mental acuity attribute",
    )

    wisdom: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=10,
        server_default="10",
        comment="Perception and insight attribute",
    )

    charisma: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=10,
        server_default="10",
        comment="Social influence attribute",
    )

    attribute_points: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Unspent attribute points for character customization",
    )

    # Currency (stored in drabs - smallest Cealdish currency unit)
    gold: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100,
        server_default="100",
        comment="Character's money in drabs (smallest unit)",
    )

    @property
    def money(self) -> int:
        """Alias for gold - returns money in drabs."""
        return self.gold

    @money.setter
    def money(self, value: int) -> None:
        """Set money in drabs."""
        self.gold = value

    # Location and progression
    current_room_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Current room key/identifier",
    )

    level: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
        comment="Character level",
    )

    experience: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Experience points",
    )

    # Combat stats
    current_hp: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=20,
        server_default="20",
        comment="Current hit points",
    )

    max_hp: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=20,
        server_default="20",
        comment="Maximum hit points",
    )

    current_mp: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=10,
        server_default="10",
        comment="Current mental energy (Alar) points",
    )

    max_mp: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=10,
        server_default="10",
        comment="Maximum mental energy (Alar) points",
    )

    # Equipment - maps slot name to item instance UUID
    # Example: {"main_hand": "uuid-here", "body": "uuid-here"}
    equipped: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
        comment="Equipped items mapping slot to item instance UUID",
    )

    # Skills - maps skill name to dict with rank and xp
    # Example: {"sympathy": {"rank": 2, "xp": 150}, "swordplay": {"rank": 1, "xp": 50}}
    skills: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
        comment="Character skills with ranks and XP",
    )

    # Visited rooms - list of room IDs the character has visited
    # Used for tracking exploration and awarding XP for first-time visits
    visited_rooms: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        server_default="[]",
        comment="List of room IDs the character has visited",
    )

    # University Arcanum rank: none, e_lir, re_lar, el_the
    arcanum_rank: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="none",
        server_default="none",
        comment="Arcanum rank at the University",
    )

    # University data stored as JSON for flexibility
    # Contains: current_term, tuition_paid, tuition_amount, admission_score, master_reputations
    university_data: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
        comment="University status data (term, tuition, reputations)",
    )

    # Cthaeh curse data - tracks pact with the Cthaeh
    # Contains: cursed, curse_accepted_at, last_bidding_time, current_target,
    #           target_type, target_expires_at, completed_biddings, failed_biddings
    cthaeh_data: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
        comment="Cthaeh curse/pact data",
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="characters",
    )

    items: Mapped[list["ItemInstance"]] = relationship(
        "ItemInstance",
        back_populates="owner",
        foreign_keys="ItemInstance.owner_id",
        cascade="all, delete-orphan",
    )

    quests: Mapped[list["Quest"]] = relationship(
        "Quest",
        back_populates="character",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        """String representation of Character."""
        return (
            f"<Character(id={self.id}, name='{self.name}', "
            f"background={self.background.value}, level={self.level})>"
        )
