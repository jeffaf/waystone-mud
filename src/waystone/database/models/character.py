"""Character model for Waystone MUD player characters."""

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
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

    # Relationship to user
    user: Mapped["User"] = relationship(
        "User",
        back_populates="characters",
    )

    def __repr__(self) -> str:
        """String representation of Character."""
        return (
            f"<Character(id={self.id}, name='{self.name}', "
            f"background={self.background.value}, level={self.level})>"
        )
