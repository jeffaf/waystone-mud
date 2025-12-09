"""NPC models for Waystone MUD."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class NPCTemplate(Base, TimestampMixin):
    """
    Template defining an NPC type (e.g., "bandit", "wolf", "merchant_imre").

    This is the blueprint for NPCs. Actual NPC instances reference this template.
    """

    __tablename__ = "npc_templates"

    id: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
        comment="Unique NPC template identifier (e.g., 'bandit', 'merchant_imre')",
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Display name of the NPC",
    )

    description: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
        comment="Full description shown when examining the NPC",
    )

    level: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment="NPC level (affects combat difficulty)",
    )

    max_hp: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=20,
        comment="Maximum hit points for this NPC type",
    )

    # Core attributes stored as JSON
    # {"strength": 12, "dexterity": 14, "constitution": 13, "intelligence": 10, "wisdom": 10, "charisma": 8}
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
        comment="D&D style attributes (str, dex, con, int, wis, cha)",
    )

    behavior: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="passive",
        comment="NPC behavior type: aggressive, passive, merchant, stationary, wander",
    )

    loot_table_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Reference to loot table for drops when killed",
    )

    # Dialogue data for interactive NPCs
    # {"greeting": "Welcome traveler!", "keywords": {"quest": "I need help...", "trade": "I buy and sell goods."}}
    dialogue: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Dialogue options: greeting, keywords, responses",
    )

    respawn_time: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=300,
        comment="Respawn time in seconds (0 = no respawn)",
    )

    def __repr__(self) -> str:
        """String representation of NPCTemplate."""
        return (
            f"<NPCTemplate(id='{self.id}', name='{self.name}', "
            f"level={self.level}, behavior='{self.behavior}')>"
        )


class NPC(Base, TimestampMixin):
    """
    An active NPC instance in the game world.

    This represents a specific NPC spawned from a template, with its own
    current state (HP, location, etc).
    """

    __tablename__ = "npcs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique NPC instance identifier",
    )

    template_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("npc_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Reference to the NPC template",
    )

    room_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Current room where this NPC is located",
    )

    current_hp: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Current hit points",
    )

    is_alive: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="Whether the NPC is currently alive",
    )

    spawned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When this NPC instance was spawned",
    )

    last_respawn: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When this NPC last respawned (for tracking respawn timer)",
    )

    def __repr__(self) -> str:
        """String representation of NPC."""
        return (
            f"<NPC(id={self.id}, template_id='{self.template_id}', "
            f"room_id='{self.room_id}', is_alive={self.is_alive})>"
        )
