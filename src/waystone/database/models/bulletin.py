"""Bulletin Board System models for Waystone MUD.

This module defines the database models for the BBS feature:
- BulletinBoard: Physical boards placed in specific rooms
- BoardMessage: Messages posted to boards
- MessageRead: Tracking which messages a character has read
- BoardAccessLevel: Enum for access control levels

The BBS system allows players and NPCs to post messages on location-based
bulletin boards with access control based on Arcanum rank and character
attributes.
"""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .character import Character


class BoardAccessLevel(enum.Enum):
    """Access levels for bulletin boards.

    These levels correspond to Arcanum ranks at the University:
    - PUBLIC: Anyone can access
    - STUDENT: University students (E'lir or higher)
    - ADVANCED: Re'lar or higher
    - MASTER: El'the or Masters only
    - PRIVATE: Specific characters only (custom logic)
    """

    PUBLIC = "public"
    STUDENT = "student"
    ADVANCED = "advanced"
    MASTER = "master"
    PRIVATE = "private"


class BulletinBoard(Base, TimestampMixin):
    """A bulletin board placed in a specific room.

    Boards are physical objects in the game world where characters
    can read and post messages. Access is controlled by Arcanum rank
    and optional attribute requirements (e.g., CHA 12+ for Eolian).

    Attributes:
        id: Unique board identifier (e.g., 'university_main')
        name: Display name of the board
        description: Description shown when examining the board
        room_id: Room where this board is located
        read_level: Minimum access level required to read messages
        post_level: Minimum access level required to post messages
        max_messages: Maximum messages before auto-pruning oldest
        allow_anonymous: Whether anonymous posting is allowed
        is_active: Whether the board is currently accepting posts
        attribute_requirement: Optional JSON string with attribute requirements
    """

    __tablename__ = "bulletin_boards"

    id: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
        comment="Unique board identifier (e.g., 'university_main', 'eolian_performers')",
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Display name of the board",
    )

    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Description shown when examining the board",
    )

    room_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Room where this board is located",
    )

    read_level: Mapped[BoardAccessLevel] = mapped_column(
        Enum(BoardAccessLevel),
        nullable=False,
        default=BoardAccessLevel.PUBLIC,
        comment="Minimum access level to read messages",
    )

    post_level: Mapped[BoardAccessLevel] = mapped_column(
        Enum(BoardAccessLevel),
        nullable=False,
        default=BoardAccessLevel.PUBLIC,
        comment="Minimum access level to post messages",
    )

    max_messages: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=50,
        comment="Maximum messages before auto-pruning oldest",
    )

    allow_anonymous: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether anonymous posting is allowed",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether the board is currently accepting posts",
    )

    # Optional attribute requirement stored as JSON string for SQLite compatibility
    # Example: '{"charisma": 12}' for Eolian board
    attribute_requirement: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Optional attribute requirements as JSON string",
    )

    # Relationships
    messages: Mapped[list["BoardMessage"]] = relationship(
        "BoardMessage",
        back_populates="board",
        cascade="all, delete-orphan",
        order_by="BoardMessage.created_at.desc()",
    )

    def __repr__(self) -> str:
        """Return string representation of BulletinBoard."""
        return f"<BulletinBoard(id='{self.id}', name='{self.name}', room='{self.room_id}')>"


class BoardMessage(Base, TimestampMixin):
    """A message posted to a bulletin board.

    Messages support threading via reply_to, pinning for important
    announcements, and optional anonymous posting. The author_name
    is preserved even if the author character is deleted.

    Attributes:
        id: Unique message identifier (UUID)
        board_id: Board this message belongs to
        author_id: Character who posted (null for NPC or deleted author)
        author_name: Preserved author name (for display after deletion)
        npc_author_id: NPC template ID if posted by NPC
        subject: Message subject line (max 80 chars)
        body: Message body content
        reply_to: Parent message ID for threading
        is_pinned: Whether message is pinned to top
        is_anonymous: Whether author is hidden in display
        board_sequence: Sequential message number on this board
    """

    __tablename__ = "board_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique message identifier",
    )

    board_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("bulletin_boards.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Board this message belongs to",
    )

    author_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("characters.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Character who posted (null for NPC or deleted author)",
    )

    author_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Preserved author name (in case character is deleted)",
    )

    npc_author_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="NPC template ID if posted by NPC",
    )

    subject: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        comment="Message subject line",
    )

    body: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Message body content",
    )

    reply_to: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("board_messages.id", ondelete="SET NULL"),
        nullable=True,
        comment="Parent message ID for threading",
    )

    is_pinned: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether message is pinned to top",
    )

    is_anonymous: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether author is hidden in display",
    )

    # Sequential number within the board (for easier reference like "read 5")
    board_sequence: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Sequential message number on this board",
    )

    # Relationships
    board: Mapped["BulletinBoard"] = relationship(
        "BulletinBoard",
        back_populates="messages",
    )

    author: Mapped["Character | None"] = relationship(
        "Character",
        foreign_keys=[author_id],
    )

    parent: Mapped["BoardMessage | None"] = relationship(
        "BoardMessage",
        remote_side=[id],
        foreign_keys=[reply_to],
    )

    def __repr__(self) -> str:
        """Return string representation of BoardMessage."""
        subject_preview = self.subject[:30] if len(self.subject) > 30 else self.subject
        return (
            f"<BoardMessage(id={self.id}, board='{self.board_id}', "
            f"seq={self.board_sequence}, subject='{subject_preview}...')>"
        )


class MessageRead(Base):
    """Tracks which messages a character has read.

    Uses a composite primary key of (character_id, message_id) for
    efficient "new message" queries. When checking for unread messages,
    we simply look for message IDs not in this table.

    Attributes:
        character_id: Character who read the message
        message_id: Message that was read
        read_at: Timestamp when the message was read
    """

    __tablename__ = "message_reads"

    character_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("characters.id", ondelete="CASCADE"),
        primary_key=True,
        comment="Character who read the message",
    )

    message_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("board_messages.id", ondelete="CASCADE"),
        primary_key=True,
        comment="Message that was read",
    )

    read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When the message was read",
    )

    def __repr__(self) -> str:
        """Return string representation of MessageRead."""
        return f"<MessageRead(char={self.character_id}, msg={self.message_id})>"
