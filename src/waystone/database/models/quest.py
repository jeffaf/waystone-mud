"""Quest model for Waystone MUD quest tracking."""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .character import Character


class QuestStatus(enum.Enum):
    """Quest status enumeration."""

    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"


class Quest(Base, TimestampMixin):
    """Player quest tracking model."""

    __tablename__ = "quests"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique quest instance identifier",
    )

    character_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("characters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Foreign key to character",
    )

    quest_template_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Quest template identifier",
    )

    status: Mapped[QuestStatus] = mapped_column(
        Enum(QuestStatus),
        nullable=False,
        default=QuestStatus.ACTIVE,
        server_default="active",
        index=True,
        comment="Current quest status",
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Timestamp when quest was started",
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when quest was completed/failed/abandoned",
    )

    # Progress tracking - stores objective completion data
    # Example: {"kill_bandits": {"current": 3, "required": 5}, "find_amulet": {"found": false}}
    progress: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
        comment="Quest objective progress tracking",
    )

    # Relationships
    character: Mapped["Character"] = relationship(
        "Character",
        back_populates="quests",
    )

    def __repr__(self) -> str:
        """String representation of Quest."""
        return (
            f"<Quest(id={self.id}, character_id={self.character_id}, "
            f"template_id='{self.quest_template_id}', status={self.status.value})>"
        )
