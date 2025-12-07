"""Room model for Waystone MUD world locations."""

from typing import Any

from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Room(Base):
    """World room/location model with exits and properties."""

    __tablename__ = "rooms"

    id: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
        comment="Unique room identifier (e.g., 'university_main_gates')",
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Display name of the room",
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Long description of the room",
    )

    area: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Area/zone identifier (e.g., 'university', 'imre')",
    )

    exits: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
        comment="JSON mapping of direction -> room_id (e.g., {'north': 'room_id', 'south': 'room_id'})",
    )

    properties: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
        comment="JSON properties/flags (e.g., {'indoor': true, 'lit': true, 'safe_zone': true})",
    )

    def __repr__(self) -> str:
        """String representation of Room."""
        return f"<Room(id='{self.id}', name='{self.name}', area='{self.area}')>"
