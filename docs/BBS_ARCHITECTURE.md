# Bulletin Board System (BBS) Architecture Specification
## Waystone MUD - Kingkiller Chronicle Theme

**Version:** 1.0
**Date:** January 25, 2025
**Author:** Architect Agent

---

## Table of Contents
1. [Executive Summary](#executive-summary)
2. [Architectural Overview](#architectural-overview)
3. [Database Models](#database-models)
4. [Game Systems](#game-systems)
5. [Command Implementations](#command-implementations)
6. [NPC Integration](#npc-integration)
7. [UI/UX Design](#uiux-design)
8. [File Structure](#file-structure)
9. [Implementation Plan](#implementation-plan)
10. [Testing Strategy](#testing-strategy)

---

## Executive Summary

### Problem Statement
The Waystone MUD needs an in-world bulletin board system that allows players and NPCs to post messages, creating immersion through thematic communication. Boards should be physical objects in specific rooms (University, Eolian, etc.) with access control based on character rank and attributes.

### Proposed Solution
A three-layer architecture following existing Waystone patterns:
1. **Database Layer**: SQLAlchemy models for boards, messages, and read tracking
2. **System Layer**: BoardManager for state, MessageFormatter for display, NPCPoster for scheduled content
3. **Command Layer**: Player commands following the existing Command pattern

### Key Design Decisions
- Boards are room-bound objects (not global)
- Access control via Arcanum rank and character attributes
- NPC posts via scheduled system with personality templates
- ANSI-style formatting adapted for MUD context
- Thread support via reply_to references (flat threading)

---

## Architectural Overview

```
                    +------------------+
                    |  Command Layer   |
                    |  (board.py)      |
                    +--------+---------+
                             |
                    +--------v---------+
                    |  System Layer    |
                    |  - BoardManager  |
                    |  - Formatter     |
                    |  - NPCPoster     |
                    +--------+---------+
                             |
                    +--------v---------+
                    |  Database Layer  |
                    |  - BulletinBoard |
                    |  - Message       |
                    |  - MessageRead   |
                    +------------------+
```

### Integration Points
- **GameEngine**: Register BBS commands, initialize BoardManager
- **Room System**: Boards linked via `room_id` foreign key
- **Character System**: Access control via `arcanum_rank` and attributes
- **NPC System**: NPCPoster scheduled via periodic cleanup task
- **University System**: Rank-based access for academic boards

---

## Database Models

### File: `src/waystone/database/models/bulletin.py`

```python
"""Bulletin Board System models for Waystone MUD."""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

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
    """Access levels for bulletin boards."""

    PUBLIC = "public"           # Anyone can read
    STUDENT = "student"         # University students (E'lir+)
    ADVANCED = "advanced"       # Re'lar+
    MASTER = "master"           # El'the or Masters only
    PRIVATE = "private"         # Specific characters only


class BulletinBoard(Base, TimestampMixin):
    """
    A bulletin board placed in a specific room.

    Boards are physical objects in the game world where characters
    can read and post messages. Access is controlled by rank and
    optional attribute requirements.
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

    # Optional attribute requirement (e.g., {"charisma": 14} for Eolian)
    attribute_requirement: Mapped[dict[str, Any] | None] = mapped_column(
        type_=String(500),  # JSON stored as string for SQLite compatibility
        nullable=True,
        comment="Optional attribute requirements as JSON",
    )

    # Relationships
    messages: Mapped[list["BoardMessage"]] = relationship(
        "BoardMessage",
        back_populates="board",
        cascade="all, delete-orphan",
        order_by="BoardMessage.created_at.desc()",
    )

    def __repr__(self) -> str:
        return f"<BulletinBoard(id='{self.id}', name='{self.name}', room='{self.room_id}')>"


class BoardMessage(Base, TimestampMixin):
    """
    A message posted to a bulletin board.

    Messages support threading via reply_to, pinning for important
    announcements, and optional anonymous posting.
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
        comment="Character who posted (null for system/deleted author)",
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
        comment="Whether author is hidden",
    )

    # Sequential number within the board (for easier reference)
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
        return (
            f"<BoardMessage(id={self.id}, board='{self.board_id}', "
            f"seq={self.board_sequence}, subject='{self.subject[:30]}...')>"
        )


class MessageRead(Base):
    """
    Tracks which messages a character has read.

    Uses a composite primary key of (character_id, message_id) for
    efficient "new message" queries.
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
        return f"<MessageRead(char={self.character_id}, msg={self.message_id})>"
```

### Model Registration

Add to `src/waystone/database/models/__init__.py`:

```python
from .bulletin import BoardAccessLevel, BoardMessage, BulletinBoard, MessageRead

__all__ = [
    # ... existing exports ...
    "BulletinBoard",
    "BoardMessage",
    "MessageRead",
    "BoardAccessLevel",
]
```

---

## Game Systems

### File: `src/waystone/game/systems/bulletin.py`

```python
"""Bulletin Board System for Waystone MUD.

Handles:
- Board access control and management
- Message creation, retrieval, and deletion
- Read tracking for new message detection
- Board pruning for message limits
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from waystone.database.engine import get_session
from waystone.database.models import Character
from waystone.database.models.bulletin import (
    BoardAccessLevel,
    BoardMessage,
    BulletinBoard,
    MessageRead,
)
from waystone.game.systems.university import ArcanumRank, rank_from_string

if TYPE_CHECKING:
    from waystone.game.engine import GameEngine

logger = structlog.get_logger(__name__)


# Access level hierarchy for comparison
ACCESS_LEVEL_ORDER = [
    BoardAccessLevel.PUBLIC,
    BoardAccessLevel.STUDENT,
    BoardAccessLevel.ADVANCED,
    BoardAccessLevel.MASTER,
    BoardAccessLevel.PRIVATE,
]


def rank_to_access_level(rank: ArcanumRank) -> BoardAccessLevel:
    """Map Arcanum rank to board access level."""
    return {
        ArcanumRank.NONE: BoardAccessLevel.PUBLIC,
        ArcanumRank.E_LIR: BoardAccessLevel.STUDENT,
        ArcanumRank.RE_LAR: BoardAccessLevel.ADVANCED,
        ArcanumRank.EL_THE: BoardAccessLevel.MASTER,
    }.get(rank, BoardAccessLevel.PUBLIC)


def can_access_board(
    character: Character,
    board: BulletinBoard,
    for_posting: bool = False,
) -> tuple[bool, str]:
    """
    Check if a character can access a board.

    Args:
        character: The character attempting access
        board: The bulletin board
        for_posting: True if checking post access, False for read access

    Returns:
        Tuple of (can_access, reason_message)
    """
    required_level = board.post_level if for_posting else board.read_level

    # Get character's access level from Arcanum rank
    char_rank = rank_from_string(character.arcanum_rank)
    char_level = rank_to_access_level(char_rank)

    # Compare access levels
    char_level_idx = ACCESS_LEVEL_ORDER.index(char_level)
    required_idx = ACCESS_LEVEL_ORDER.index(required_level)

    if char_level_idx < required_idx:
        action = "post to" if for_posting else "read"
        return (False, f"You lack the rank required to {action} this board.")

    # Check attribute requirements if present
    if board.attribute_requirement:
        import json
        try:
            requirements = json.loads(board.attribute_requirement) if isinstance(
                board.attribute_requirement, str
            ) else board.attribute_requirement

            for attr, required_value in requirements.items():
                char_value = getattr(character, attr, 0)
                if char_value < required_value:
                    return (False, f"This board requires {attr.title()} of {required_value}.")
        except (json.JSONDecodeError, TypeError):
            pass  # Invalid requirements, allow access

    return (True, "")


@dataclass
class BoardSummary:
    """Summary information about a board."""
    id: str
    name: str
    description: str
    total_messages: int
    unread_count: int
    last_post_at: datetime | None


async def get_boards_in_room(
    room_id: str,
    character_id: UUID | None = None,
) -> list[BoardSummary]:
    """
    Get all boards in a room with message counts.

    Args:
        room_id: Room identifier
        character_id: Optional character for unread counts

    Returns:
        List of BoardSummary objects
    """
    summaries = []

    try:
        async with get_session() as session:
            # Get boards in room
            result = await session.execute(
                select(BulletinBoard)
                .where(BulletinBoard.room_id == room_id)
                .where(BulletinBoard.is_active == True)
            )
            boards = list(result.scalars().all())

            for board in boards:
                # Count total messages
                count_result = await session.execute(
                    select(func.count(BoardMessage.id))
                    .where(BoardMessage.board_id == board.id)
                )
                total_messages = count_result.scalar() or 0

                # Get last post timestamp
                last_result = await session.execute(
                    select(func.max(BoardMessage.created_at))
                    .where(BoardMessage.board_id == board.id)
                )
                last_post_at = last_result.scalar()

                # Count unread if character provided
                unread_count = 0
                if character_id:
                    unread_result = await session.execute(
                        select(func.count(BoardMessage.id))
                        .where(BoardMessage.board_id == board.id)
                        .where(~BoardMessage.id.in_(
                            select(MessageRead.message_id)
                            .where(MessageRead.character_id == character_id)
                        ))
                    )
                    unread_count = unread_result.scalar() or 0

                summaries.append(BoardSummary(
                    id=board.id,
                    name=board.name,
                    description=board.description,
                    total_messages=total_messages,
                    unread_count=unread_count,
                    last_post_at=last_post_at,
                ))

    except Exception as e:
        logger.error(
            "get_boards_in_room_failed",
            room_id=room_id,
            error=str(e),
            exc_info=True,
        )

    return summaries


async def get_board(board_id: str) -> BulletinBoard | None:
    """Get a board by ID."""
    try:
        async with get_session() as session:
            result = await session.execute(
                select(BulletinBoard).where(BulletinBoard.id == board_id)
            )
            return result.scalar_one_or_none()
    except Exception as e:
        logger.error("get_board_failed", board_id=board_id, error=str(e))
        return None


async def get_board_in_room(room_id: str, board_name: str) -> BulletinBoard | None:
    """Get a board in a specific room by name (partial match)."""
    try:
        async with get_session() as session:
            # Try exact match first
            result = await session.execute(
                select(BulletinBoard)
                .where(BulletinBoard.room_id == room_id)
                .where(func.lower(BulletinBoard.name) == board_name.lower())
            )
            board = result.scalar_one_or_none()

            if board:
                return board

            # Try partial match
            result = await session.execute(
                select(BulletinBoard)
                .where(BulletinBoard.room_id == room_id)
                .where(func.lower(BulletinBoard.name).contains(board_name.lower()))
            )
            return result.scalars().first()
    except Exception as e:
        logger.error(
            "get_board_in_room_failed",
            room_id=room_id,
            board_name=board_name,
            error=str(e),
        )
        return None


@dataclass
class MessageSummary:
    """Summary of a message for list display."""
    id: UUID
    sequence: int
    subject: str
    author_name: str
    is_anonymous: bool
    is_pinned: bool
    created_at: datetime
    is_unread: bool
    reply_to_seq: int | None


async def list_messages(
    board_id: str,
    character_id: UUID | None = None,
    limit: int = 20,
    offset: int = 0,
    unread_only: bool = False,
) -> list[MessageSummary]:
    """
    List messages on a board.

    Args:
        board_id: Board identifier
        character_id: Optional character for unread tracking
        limit: Maximum messages to return
        offset: Starting offset for pagination
        unread_only: If True, only return unread messages

    Returns:
        List of MessageSummary objects
    """
    summaries = []

    try:
        async with get_session() as session:
            # Build query
            query = (
                select(BoardMessage)
                .where(BoardMessage.board_id == board_id)
                .order_by(BoardMessage.is_pinned.desc())  # Pinned first
                .order_by(BoardMessage.created_at.desc())
            )

            if unread_only and character_id:
                query = query.where(
                    ~BoardMessage.id.in_(
                        select(MessageRead.message_id)
                        .where(MessageRead.character_id == character_id)
                    )
                )

            query = query.limit(limit).offset(offset)

            result = await session.execute(query)
            messages = list(result.scalars().all())

            # Get read status for all messages
            read_message_ids = set()
            if character_id:
                message_ids = [m.id for m in messages]
                if message_ids:
                    read_result = await session.execute(
                        select(MessageRead.message_id)
                        .where(MessageRead.character_id == character_id)
                        .where(MessageRead.message_id.in_(message_ids))
                    )
                    read_message_ids = {row[0] for row in read_result.all()}

            # Build parent sequence lookup for replies
            parent_sequences = {}
            reply_parent_ids = [m.reply_to for m in messages if m.reply_to]
            if reply_parent_ids:
                parent_result = await session.execute(
                    select(BoardMessage.id, BoardMessage.board_sequence)
                    .where(BoardMessage.id.in_(reply_parent_ids))
                )
                parent_sequences = {row[0]: row[1] for row in parent_result.all()}

            for msg in messages:
                summaries.append(MessageSummary(
                    id=msg.id,
                    sequence=msg.board_sequence,
                    subject=msg.subject,
                    author_name="Anonymous" if msg.is_anonymous else msg.author_name,
                    is_anonymous=msg.is_anonymous,
                    is_pinned=msg.is_pinned,
                    created_at=msg.created_at,
                    is_unread=msg.id not in read_message_ids,
                    reply_to_seq=parent_sequences.get(msg.reply_to) if msg.reply_to else None,
                ))

    except Exception as e:
        logger.error(
            "list_messages_failed",
            board_id=board_id,
            error=str(e),
            exc_info=True,
        )

    return summaries


async def get_message(
    board_id: str,
    sequence: int,
) -> BoardMessage | None:
    """Get a message by board and sequence number."""
    try:
        async with get_session() as session:
            result = await session.execute(
                select(BoardMessage)
                .where(BoardMessage.board_id == board_id)
                .where(BoardMessage.board_sequence == sequence)
            )
            return result.scalar_one_or_none()
    except Exception as e:
        logger.error(
            "get_message_failed",
            board_id=board_id,
            sequence=sequence,
            error=str(e),
        )
        return None


async def mark_message_read(
    character_id: UUID,
    message_id: UUID,
) -> None:
    """Mark a message as read by a character."""
    try:
        async with get_session() as session:
            # Check if already read
            existing = await session.execute(
                select(MessageRead)
                .where(MessageRead.character_id == character_id)
                .where(MessageRead.message_id == message_id)
            )
            if existing.scalar_one_or_none():
                return  # Already read

            # Create read record
            read_record = MessageRead(
                character_id=character_id,
                message_id=message_id,
            )
            session.add(read_record)
            await session.commit()
    except Exception as e:
        logger.error(
            "mark_message_read_failed",
            character_id=str(character_id),
            message_id=str(message_id),
            error=str(e),
        )


async def post_message(
    board_id: str,
    author_id: UUID | None,
    author_name: str,
    subject: str,
    body: str,
    reply_to_seq: int | None = None,
    is_anonymous: bool = False,
    npc_author_id: str | None = None,
) -> tuple[bool, str, BoardMessage | None]:
    """
    Post a new message to a board.

    Args:
        board_id: Target board ID
        author_id: Character UUID (None for NPC posts)
        author_name: Display name of author
        subject: Message subject
        body: Message body
        reply_to_seq: Optional parent message sequence number
        is_anonymous: Whether to hide author
        npc_author_id: NPC template ID if NPC post

    Returns:
        Tuple of (success, message, BoardMessage)
    """
    try:
        async with get_session() as session:
            # Get board
            board_result = await session.execute(
                select(BulletinBoard).where(BulletinBoard.id == board_id)
            )
            board = board_result.scalar_one_or_none()

            if not board:
                return (False, "Board not found.", None)

            if not board.is_active:
                return (False, "This board is not accepting new posts.", None)

            # Check anonymous posting
            if is_anonymous and not board.allow_anonymous:
                return (False, "Anonymous posting is not allowed on this board.", None)

            # Get next sequence number
            seq_result = await session.execute(
                select(func.coalesce(func.max(BoardMessage.board_sequence), 0))
                .where(BoardMessage.board_id == board_id)
            )
            next_seq = (seq_result.scalar() or 0) + 1

            # Get reply_to ID if replying
            reply_to_id = None
            if reply_to_seq:
                parent_result = await session.execute(
                    select(BoardMessage.id)
                    .where(BoardMessage.board_id == board_id)
                    .where(BoardMessage.board_sequence == reply_to_seq)
                )
                parent = parent_result.scalar_one_or_none()
                if parent:
                    reply_to_id = parent

            # Create message
            message = BoardMessage(
                board_id=board_id,
                author_id=author_id,
                author_name=author_name,
                npc_author_id=npc_author_id,
                subject=subject,
                body=body,
                reply_to=reply_to_id,
                is_anonymous=is_anonymous,
                board_sequence=next_seq,
            )
            session.add(message)

            # Prune old messages if over limit
            count_result = await session.execute(
                select(func.count(BoardMessage.id))
                .where(BoardMessage.board_id == board_id)
            )
            message_count = (count_result.scalar() or 0) + 1  # +1 for new message

            if message_count > board.max_messages:
                # Delete oldest non-pinned messages
                to_delete = message_count - board.max_messages
                oldest_result = await session.execute(
                    select(BoardMessage.id)
                    .where(BoardMessage.board_id == board_id)
                    .where(BoardMessage.is_pinned == False)
                    .order_by(BoardMessage.created_at.asc())
                    .limit(to_delete)
                )
                old_ids = [row[0] for row in oldest_result.all()]
                if old_ids:
                    # Delete associated read records first
                    await session.execute(
                        MessageRead.__table__.delete().where(
                            MessageRead.message_id.in_(old_ids)
                        )
                    )
                    # Delete messages
                    await session.execute(
                        BoardMessage.__table__.delete().where(
                            BoardMessage.id.in_(old_ids)
                        )
                    )

            await session.commit()
            await session.refresh(message)

            logger.info(
                "message_posted",
                board_id=board_id,
                message_id=str(message.id),
                author_name=author_name,
                subject=subject,
            )

            return (True, f"Message #{next_seq} posted.", message)

    except Exception as e:
        logger.error(
            "post_message_failed",
            board_id=board_id,
            author_name=author_name,
            error=str(e),
            exc_info=True,
        )
        return (False, "Failed to post message. Please try again.", None)


async def delete_message(
    board_id: str,
    sequence: int,
    character_id: UUID,
    is_moderator: bool = False,
) -> tuple[bool, str]:
    """
    Delete a message from a board.

    Args:
        board_id: Board identifier
        sequence: Message sequence number
        character_id: Character attempting deletion
        is_moderator: Whether character has moderator powers

    Returns:
        Tuple of (success, message)
    """
    try:
        async with get_session() as session:
            result = await session.execute(
                select(BoardMessage)
                .where(BoardMessage.board_id == board_id)
                .where(BoardMessage.board_sequence == sequence)
            )
            message = result.scalar_one_or_none()

            if not message:
                return (False, f"Message #{sequence} not found.")

            # Check ownership or moderator status
            if message.author_id != character_id and not is_moderator:
                return (False, "You can only remove your own messages.")

            # Delete read records
            await session.execute(
                MessageRead.__table__.delete().where(
                    MessageRead.message_id == message.id
                )
            )

            # Delete message
            await session.delete(message)
            await session.commit()

            logger.info(
                "message_deleted",
                board_id=board_id,
                sequence=sequence,
                deleted_by=str(character_id),
            )

            return (True, f"Message #{sequence} removed.")

    except Exception as e:
        logger.error(
            "delete_message_failed",
            board_id=board_id,
            sequence=sequence,
            error=str(e),
        )
        return (False, "Failed to remove message. Please try again.")


async def pin_message(
    board_id: str,
    sequence: int,
    pin: bool = True,
) -> tuple[bool, str]:
    """Pin or unpin a message."""
    try:
        async with get_session() as session:
            result = await session.execute(
                select(BoardMessage)
                .where(BoardMessage.board_id == board_id)
                .where(BoardMessage.board_sequence == sequence)
            )
            message = result.scalar_one_or_none()

            if not message:
                return (False, f"Message #{sequence} not found.")

            message.is_pinned = pin
            await session.commit()

            action = "pinned" if pin else "unpinned"
            return (True, f"Message #{sequence} {action}.")

    except Exception as e:
        logger.error(
            "pin_message_failed",
            board_id=board_id,
            sequence=sequence,
            error=str(e),
        )
        return (False, "Failed to update message. Please try again.")


# Board definitions (can later be loaded from YAML)
BOARD_DEFINITIONS: list[dict[str, Any]] = [
    # University Boards
    {
        "id": "university_main",
        "name": "University Notice Board",
        "description": "The main notice board of the University, covered with announcements, schedules, and official postings.",
        "room_id": "university_courtyard",
        "read_level": "public",
        "post_level": "student",
        "max_messages": 50,
    },
    {
        "id": "university_admissions",
        "name": "Admissions Board",
        "description": "A board dedicated to admissions information, tuition announcements, and enrollment notices.",
        "room_id": "university_hollows",
        "read_level": "public",
        "post_level": "master",
        "max_messages": 30,
    },
    {
        "id": "archives_research",
        "name": "Research Requests",
        "description": "A board for posting and claiming research requests in the Archives.",
        "room_id": "university_archives",
        "read_level": "student",
        "post_level": "advanced",
        "max_messages": 40,
    },
    {
        "id": "artificery_commissions",
        "name": "Artificer's Guild Board",
        "description": "Commission requests and sale postings for artificed items.",
        "room_id": "university_artificery",
        "read_level": "public",
        "post_level": "student",
        "max_messages": 40,
    },
    # Imre Boards
    {
        "id": "eolian_performers",
        "name": "Eolian Performance Board",
        "description": "A tastefully decorated board listing upcoming performances and audition times.",
        "room_id": "imre_eolian",
        "read_level": "public",
        "post_level": "public",
        "max_messages": 30,
        "attribute_requirement": '{"charisma": 12}',  # Must have CHA 12+ to post
    },
    {
        "id": "imre_marketplace",
        "name": "Imre Marketplace Board",
        "description": "A weathered board full of buy/sell notices and wanted postings.",
        "room_id": "imre_main_square",
        "read_level": "public",
        "post_level": "public",
        "max_messages": 60,
    },
    {
        "id": "imre_courier",
        "name": "Courier Board",
        "description": "Delivery notices and messages for travelers.",
        "room_id": "imre_main_gate",
        "read_level": "public",
        "post_level": "public",
        "max_messages": 40,
        "allow_anonymous": True,
    },
]


async def initialize_boards() -> int:
    """
    Initialize predefined boards in the database.

    Returns:
        Number of boards created
    """
    created = 0

    try:
        async with get_session() as session:
            for board_def in BOARD_DEFINITIONS:
                # Check if board exists
                existing = await session.execute(
                    select(BulletinBoard).where(BulletinBoard.id == board_def["id"])
                )
                if existing.scalar_one_or_none():
                    continue

                # Create board
                board = BulletinBoard(
                    id=board_def["id"],
                    name=board_def["name"],
                    description=board_def["description"],
                    room_id=board_def["room_id"],
                    read_level=BoardAccessLevel[board_def.get("read_level", "public").upper()],
                    post_level=BoardAccessLevel[board_def.get("post_level", "public").upper()],
                    max_messages=board_def.get("max_messages", 50),
                    allow_anonymous=board_def.get("allow_anonymous", False),
                    attribute_requirement=board_def.get("attribute_requirement"),
                )
                session.add(board)
                created += 1

            await session.commit()

            if created:
                logger.info("bulletin_boards_initialized", count=created)

    except Exception as e:
        logger.error("initialize_boards_failed", error=str(e), exc_info=True)

    return created
```

---

## NPC Posting System

### File: `src/waystone/game/systems/npc_poster.py`

```python
"""NPC Poster System for Waystone MUD.

Handles scheduled NPC posts to bulletin boards with character-appropriate
writing styles and content.
"""

import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from waystone.game.systems.bulletin import post_message

logger = structlog.get_logger(__name__)


@dataclass
class NPCPostTemplate:
    """Template for NPC posts with subject/body patterns."""

    subject_patterns: list[str]
    body_patterns: list[str]

    def generate_subject(self, **kwargs: Any) -> str:
        """Generate a subject line from patterns."""
        pattern = random.choice(self.subject_patterns)
        return pattern.format(**kwargs)

    def generate_body(self, **kwargs: Any) -> str:
        """Generate a message body from patterns."""
        pattern = random.choice(self.body_patterns)
        return pattern.format(**kwargs)


@dataclass
class NPCPostingSchedule:
    """Schedule configuration for an NPC poster."""

    npc_template_id: str
    npc_name: str
    board_id: str
    min_interval_hours: int = 24  # Minimum hours between posts
    max_interval_hours: int = 72  # Maximum hours between posts
    active_hours: tuple[int, int] = (6, 22)  # Hours when NPC posts (6am-10pm)
    probability: float = 0.3  # Probability of posting when checked
    templates: list[NPCPostTemplate] = field(default_factory=list)
    last_post_at: datetime | None = None
    next_post_after: datetime | None = None

    def should_post(self, current_time: datetime) -> bool:
        """Check if NPC should post at current time."""
        hour = current_time.hour
        if not (self.active_hours[0] <= hour < self.active_hours[1]):
            return False

        if self.next_post_after and current_time < self.next_post_after:
            return False

        return random.random() < self.probability

    def record_post(self, current_time: datetime) -> None:
        """Record that a post was made."""
        self.last_post_at = current_time
        interval = random.randint(self.min_interval_hours, self.max_interval_hours)
        self.next_post_after = current_time + timedelta(hours=interval)


# NPC Personality Templates
ELODIN_TEMPLATES = [
    NPCPostTemplate(
        subject_patterns=[
            "Wind",
            "Names",
            "A Thought",
            "Class {action}",
            "Regarding Doors",
            "Stone and Moon",
        ],
        body_patterns=[
            "The name of the wind is not a name.\nThink on this. Or don't.\nI certainly won't.\n\n(This message brought to you by the Department of Naming,\nwhich does not exist, officially.)",
            "Today's Naming session is {status} because I have\nmisplaced my {item}. Also because naming is not something\nyou can schedule on a {day} afternoon.\n\nThose seeking enlightenment may find me on the roof\nof the Mews. Or perhaps I will find you.\n\nNo, probably the roof thing.",
            "A stone knows its name. Does the wind?\n\nThe wind knows nothing. That is its name.\n\nDo not reply to this message.",
            "I saw a student attempting to memorize today.\nHow dreadfully sad.\n\nMemory is a poor substitute for understanding.\nUnderstanding is a poor substitute for knowing.\nKnowing requires no substitute.\n\n- E",
            "The four-plate door does not want to be opened.\nThis is obvious to anyone who has asked it nicely.\n\nStop trying to pick the lock.\nThere is no lock.",
        ],
    ),
]

AMBROSE_TEMPLATES = [
    NPCPostTemplate(
        subject_patterns=[
            "Re: Standards",
            "Commoner Infestation",
            "Eolian Performance - {day}",
            "A Reminder of Propriety",
            "Regarding the Incident",
        ],
        body_patterns=[
            "It has come to my attention that certain scholarship\nstudents have been using the Artificery as their personal\nworkshop, leaving their crude projects scattered about\nlike refuse.\n\nThose of proper breeding should not have to navigate\naround the detritus of the lower classes.\n\nThis is beneath the standards of the Arcanum.\n\n                        - Ambrose Jakis\n                          House Jakis, Vintas",
            "I shall be performing at the Eolian this {day} eve.\nThose of refined taste are welcome to attend.\n\nNaturally, the talent pipes shall be mine by evening's end.\n\n                        - Ambrose Jakis\n                          Patron of the Arts",
            "To the individual who displaced my belongings\nfrom my usual table at the Eolian:\n\nYou know who you are. Know also that House Jakis\nhas a long memory and considerable influence.\n\n                        - A. Jakis",
            "Another day, another commoner pretending to belong\namongst their betters. How tiresome.\n\nPerhaps admissions should consider family lineage\nin addition to mere academic potential.\n\n                        - Ambrose Jakis\n                          Twelfth in line to the throne of Vintas",
        ],
    ),
]

KILVIN_TEMPLATES = [
    NPCPostTemplate(
        subject_patterns=[
            "Workshop Schedule",
            "SAFETY REMINDER",
            "Sygaldry Supplies",
            "Commission Queue",
            "Lost: {item}",
        ],
        body_patterns=[
            "ATTENTION STUDENTS:\n\nThe Artificery workshop will be closed on {day}\nfor maintenance of the great forge.\n\nNo exceptions will be made.\nPlan your projects accordingly.\n\n- Master Kilvin",
            "SAFETY NOTICE:\n\nI must remind all students that combining\nthe runes for heat and containment on the\nsame object without proper slippage calculations\nis FORBIDDEN.\n\nThe scorch marks on the ceiling should serve\nas adequate reminder of why.\n\n- Master Kilvin",
            "The following sygaldry supplies are now available:\n\n  - Copper wire (grade A): {price_1} talents/span\n  - Iron blanks (small): {price_2} jots each\n  - Heat-source gems: BACKORDERED\n\nSee Scriv Jaxim for purchases.\n\n- Master Kilvin",
            "WORKSHOP RULES (Annual Reminder):\n\n1. No sympathy work near the coal bins.\n2. All bindings must be documented BEFORE creation.\n3. Exploded projects must be reported within the hour.\n4. The forge is not for cooking.\n5. Clean your workspace or lose your workspace.\n\n- Master Kilvin",
        ],
    ),
]

LORREN_TEMPLATES = [
    NPCPostTemplate(
        subject_patterns=[
            "Archives Policy Update",
            "New Acquisitions",
            "SILENCE REMINDER",
            "Restricted Section Hours",
            "Missing Volume",
        ],
        body_patterns=[
            "ARCHIVES POLICY UPDATE:\n\nEffective immediately, all students must present their\nArchives tile before entering Stacks Level 2 and below.\n\nThose without proper authorization will be escorted out\nand their access privileges reviewed.\n\n                                        - Master Lorren\n                                          Chancellor",
            "NEW ACQUISITIONS - {month}:\n\nThe Archives has acquired the following volumes:\n\n  - 'Principles of Sympathy' (4th ed.) - 3 copies\n  - 'Cealdish Mercantile Practices' - 1 copy\n  - 'Fauna of the Eld' (illustrated) - 1 copy\n\nSee the acquisition desk for availability.\n\n                                        - Master Lorren",
            "REMINDER:\n\nThe Archives is a place of SILENCE.\n\nWhispering is not silence.\nRustling is not silence.\nThinking loudly is not silence.\n\nViolators will be removed.\n\n                                        - Master Lorren",
            "The following volume is MISSING:\n\n  'En Temerant Voistra' - Folio IV\n\nAny information regarding its whereabouts should be\nreported to a Scriv immediately.\n\nRemember: late returns are noted. Forever.\n\n                                        - Master Lorren",
        ],
    ),
]

SIMMON_TEMPLATES = [
    NPCPostTemplate(
        subject_patterns=[
            "Equipment for Sale",
            "Study Group - {subject}",
            "Lost: Brown Leather Pouch",
            "Seeking Tutor",
            "Eolian Tonight?",
        ],
        body_patterns=[
            "Hey everyone!\n\nI have the following items available for sale,\nall in excellent condition:\n\n  - Sympathy lamp (barely used)     - 3 talents\n  - Set of binding cables           - 1 talent, 2 jots\n  - Mommet-grade wax (2 blocks)     - 4 jots each\n\nFind me at the Artificery workshop most afternoons.\n\n                                        - Simmon",
            "Anyone interested in forming a study group for\n{subject}? Master {master}'s exams are notoriously\ndifficult and I figure we could help each other out.\n\nMeeting at the Mews common room, {day} evening.\nBring notes and snacks!\n\n                                        - Simmon",
            "Has anyone seen a brown leather pouch?\n\nI think I left it in the Medica or possibly the\nlecture hall. Contains some personal items and\nabout 8 jots.\n\nReward for return! (More if the jots are still there.)\n\n                                        - Simmon\n                                          Usually at Mews",
            "Heading to the Eolian tonight if anyone wants\nto join! Supposedly there's a new performer from\nAtur trying for their pipes.\n\nFirst round's on me if you can beat me at corners.\n\n                                        - Sim",
        ],
    ),
]


# Posting schedules for each NPC
NPC_POSTING_SCHEDULES: list[NPCPostingSchedule] = [
    NPCPostingSchedule(
        npc_template_id="elodin",
        npc_name="Master Elodin",
        board_id="university_main",
        min_interval_hours=48,
        max_interval_hours=168,  # 1 week max
        active_hours=(0, 24),  # Elodin posts at any hour
        probability=0.2,
        templates=ELODIN_TEMPLATES,
    ),
    NPCPostingSchedule(
        npc_template_id="ambrose",
        npc_name="Ambrose Jakis",
        board_id="university_main",
        min_interval_hours=24,
        max_interval_hours=72,
        active_hours=(10, 22),
        probability=0.25,
        templates=AMBROSE_TEMPLATES,
    ),
    NPCPostingSchedule(
        npc_template_id="ambrose",
        npc_name="Ambrose Jakis",
        board_id="eolian_performers",
        min_interval_hours=72,
        max_interval_hours=168,
        active_hours=(14, 20),
        probability=0.15,
        templates=AMBROSE_TEMPLATES,
    ),
    NPCPostingSchedule(
        npc_template_id="master_kilvin",
        npc_name="Master Kilvin",
        board_id="artificery_commissions",
        min_interval_hours=24,
        max_interval_hours=96,
        active_hours=(6, 20),
        probability=0.3,
        templates=KILVIN_TEMPLATES,
    ),
    NPCPostingSchedule(
        npc_template_id="master_lorren",
        npc_name="Master Lorren",
        board_id="archives_research",
        min_interval_hours=72,
        max_interval_hours=168,
        active_hours=(8, 18),
        probability=0.2,
        templates=LORREN_TEMPLATES,
    ),
    NPCPostingSchedule(
        npc_template_id="simmon",
        npc_name="Simmon",
        board_id="university_main",
        min_interval_hours=24,
        max_interval_hours=72,
        active_hours=(9, 23),
        probability=0.3,
        templates=SIMMON_TEMPLATES,
    ),
    NPCPostingSchedule(
        npc_template_id="simmon",
        npc_name="Simmon",
        board_id="imre_marketplace",
        min_interval_hours=48,
        max_interval_hours=120,
        active_hours=(10, 20),
        probability=0.2,
        templates=SIMMON_TEMPLATES,
    ),
]


def _get_template_variables() -> dict[str, Any]:
    """Get random variables for template substitution."""
    days = ["Luten", "Shuden", "Theden", "Feochen", "Orden", "Hepten", "Chaen", "Felling", "Reaving", "Cendling", "Mourning"]
    months = ["Thaw", "Equis", "Caitelyn", "Solace", "Lannis", "Reaping", "Fallow", "Dearth"]
    items = ["shoes", "hat", "keys", "lunch", "students", "chalk", "motivation"]
    subjects = ["Sympathy", "Alchemy", "Artificery", "Rhetoric", "History", "Medica"]
    masters = ["Hemme", "Kilvin", "Arwyl", "Brandeur", "Mandrag"]

    return {
        "day": random.choice(days),
        "month": random.choice(months),
        "item": random.choice(items),
        "subject": random.choice(subjects),
        "master": random.choice(masters),
        "status": random.choice(["cancelled", "relocated", "optional", "mandatory"]),
        "action": random.choice(["Cancelled", "Relocated", "Optional Today"]),
        "price_1": random.randint(2, 5),
        "price_2": random.randint(3, 8),
    }


async def check_npc_posts() -> int:
    """
    Check all NPC posting schedules and create posts as needed.

    Should be called periodically (e.g., every 30 minutes).

    Returns:
        Number of posts created
    """
    posts_created = 0
    current_time = datetime.now(UTC)

    for schedule in NPC_POSTING_SCHEDULES:
        if not schedule.should_post(current_time):
            continue

        if not schedule.templates:
            continue

        # Select random template
        template = random.choice(schedule.templates[0].subject_patterns)
        post_template = schedule.templates[0]

        # Generate content
        variables = _get_template_variables()
        subject = post_template.generate_subject(**variables)
        body = post_template.generate_body(**variables)

        # Post message
        success, msg, _ = await post_message(
            board_id=schedule.board_id,
            author_id=None,
            author_name=schedule.npc_name,
            subject=subject,
            body=body,
            npc_author_id=schedule.npc_template_id,
        )

        if success:
            schedule.record_post(current_time)
            posts_created += 1

            logger.info(
                "npc_post_created",
                npc=schedule.npc_name,
                board=schedule.board_id,
                subject=subject,
            )

    return posts_created
```

---

## Command Implementations

### File: `src/waystone/game/commands/board.py`

```python
"""Bulletin Board commands for Waystone MUD."""

from uuid import UUID

import structlog
from sqlalchemy import select

from waystone.database.engine import get_session
from waystone.database.models import Character
from waystone.game.systems.bulletin import (
    can_access_board,
    delete_message,
    get_board,
    get_board_in_room,
    get_boards_in_room,
    get_message,
    list_messages,
    mark_message_read,
    pin_message,
    post_message,
)
from waystone.game.systems.university import ArcanumRank, rank_from_string
from waystone.network import colorize

from .base import Command, CommandContext

logger = structlog.get_logger(__name__)


# Session state for board context
_character_board_context: dict[str, str] = {}  # character_id -> board_id
_character_message_position: dict[str, int] = {}  # character_id -> current message seq


def _format_board_header(name: str, total: int, unread: int) -> list[str]:
    """Format board header display."""
    lines = []
    lines.append(colorize(".=========================================================.", "CYAN"))
    lines.append(colorize("|", "CYAN") + f"              {name.upper():^38}" + colorize("|", "CYAN"))
    lines.append(colorize("|=========================================================|", "CYAN"))
    stats = f"{total} messages ({unread} new)" if unread else f"{total} messages"
    lines.append(colorize("|", "CYAN") + f" {stats:<55}" + colorize("|", "CYAN"))
    lines.append(colorize("'---------------------------------------------------------'", "CYAN"))
    return lines


def _format_message_list_header() -> str:
    """Format header for message list."""
    return (
        colorize(" #  ", "YELLOW") +
        colorize("Subject", "WHITE") + " " * 27 +
        colorize("Author", "WHITE") + " " * 9 +
        colorize("Date", "WHITE")
    )


def _format_message_row(msg: "MessageSummary") -> str:
    """Format a single message row."""
    # Indicators
    new_marker = colorize("[NEW]", "GREEN") if msg.is_unread else "     "
    pin_marker = colorize("[PIN]", "YELLOW") if msg.is_pinned else ""

    # Truncate subject
    max_subject = 30
    subject = msg.subject[:max_subject] + "..." if len(msg.subject) > max_subject else msg.subject
    if msg.reply_to_seq:
        subject = f"Re: {subject}"[:max_subject]

    # Format author
    author = msg.author_name[:14]

    # Format date
    date_str = msg.created_at.strftime("%b %d")

    # Sequence number
    seq = f"{msg.sequence:3d}"

    return f"{new_marker} {seq} {pin_marker}{subject:<32} {author:<14} {date_str}"


def _format_message_display(msg: "BoardMessage", seq: int, total: int) -> list[str]:
    """Format a full message display."""
    lines = []
    lines.append(colorize(".=========================================================.", "CYAN"))
    lines.append(
        colorize("|", "CYAN") +
        f" Message #{seq} of {total}" + " " * (47 - len(str(seq)) - len(str(total))) +
        colorize("|", "CYAN")
    )
    lines.append(colorize("|=========================================================|", "CYAN"))

    author = "Anonymous" if msg.is_anonymous else msg.author_name
    date_str = msg.created_at.strftime("%A, %d %B")

    lines.append(colorize("|", "CYAN") + f" From: {author:<49}" + colorize("|", "CYAN"))
    lines.append(colorize("|", "CYAN") + f" Date: {date_str:<49}" + colorize("|", "CYAN"))
    lines.append(colorize("|", "CYAN") + f" Subj: {msg.subject:<49}" + colorize("|", "CYAN"))
    lines.append(colorize("'---------------------------------------------------------'", "CYAN"))
    lines.append("")

    # Body with word wrap
    for line in msg.body.split("\n"):
        lines.append(line)

    lines.append("")
    lines.append(colorize(".=========================================================.", "CYAN"))
    lines.append(colorize("[R]eply  [N]ext  [P]rev  [L]ist  [Q]uit", "YELLOW"))

    return lines


class BoardCommand(Command):
    """View bulletin boards in the current room."""

    name = "board"
    aliases = ["boards", "bb"]
    help_text = "board [name] - View boards or select a board"
    extended_help = """
BOARD - Bulletin Board System

Usage:
  board           - List all boards in the current room
  board <name>    - Select a board to read/post messages

Once you've selected a board, use these commands:
  list [new]      - List messages (optionally only new ones)
  read [#|new]    - Read a message by number or next new
  post <subject>  - Start composing a new message
  reply <#>       - Reply to a message
  remove <#>      - Remove your own message

Examples:
  board notice    - Select the notice board
  list new        - Show only unread messages
  read 5          - Read message #5
  post Selling    - Start a post with subject "Selling"
"""

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the board command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(
                colorize("You must be playing a character to use boards.", "RED")
            )
            return

        try:
            async with get_session() as session:
                result = await session.execute(
                    select(Character).where(Character.id == UUID(ctx.session.character_id))
                )
                character = result.scalar_one_or_none()

                if not character:
                    await ctx.connection.send_line(colorize("Character not found.", "RED"))
                    return

                room_id = character.current_room_id
                char_id = UUID(ctx.session.character_id)

                if not ctx.args:
                    # List boards in room
                    boards = await get_boards_in_room(room_id, char_id)

                    if not boards:
                        await ctx.connection.send_line(
                            colorize("There are no bulletin boards here.", "YELLOW")
                        )
                        return

                    await ctx.connection.send_line(colorize("\nBulletin Boards:", "CYAN"))
                    await ctx.connection.send_line("-" * 50)

                    for board in boards:
                        unread = f" ({board.unread_count} new)" if board.unread_count else ""
                        await ctx.connection.send_line(
                            f"  {colorize(board.name, 'YELLOW')}{unread}"
                        )
                        await ctx.connection.send_line(
                            f"    {board.description[:60]}..."
                        )

                    await ctx.connection.send_line("")
                    await ctx.connection.send_line(
                        colorize("Type 'board <name>' to select a board.", "DIM")
                    )
                else:
                    # Select a board
                    board_name = " ".join(ctx.args)
                    board = await get_board_in_room(room_id, board_name)

                    if not board:
                        await ctx.connection.send_line(
                            colorize(f"No board matching '{board_name}' found here.", "RED")
                        )
                        return

                    # Check access
                    can_read, reason = can_access_board(character, board, for_posting=False)
                    if not can_read:
                        await ctx.connection.send_line(colorize(reason, "RED"))
                        return

                    # Set context
                    _character_board_context[ctx.session.character_id] = board.id

                    # Show board summary
                    summaries = await get_boards_in_room(room_id, char_id)
                    board_summary = next((b for b in summaries if b.id == board.id), None)

                    total = board_summary.total_messages if board_summary else 0
                    unread = board_summary.unread_count if board_summary else 0

                    for line in _format_board_header(board.name, total, unread):
                        await ctx.connection.send_line(line)

                    await ctx.connection.send_line("")
                    await ctx.connection.send_line(
                        colorize("Commands: list, read, post, reply, remove", "DIM")
                    )

        except Exception as e:
            logger.error("board_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Failed to access boards. Please try again.", "RED")
            )


class ListCommand(Command):
    """List messages on the current board."""

    name = "list"
    aliases = ["messages", "ls"]
    help_text = "list [new] - List messages on current board"

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the list command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(
                colorize("You must be playing a character.", "RED")
            )
            return

        board_id = _character_board_context.get(ctx.session.character_id)
        if not board_id:
            await ctx.connection.send_line(
                colorize("Select a board first with 'board <name>'.", "YELLOW")
            )
            return

        unread_only = ctx.args and ctx.args[0].lower() == "new"
        char_id = UUID(ctx.session.character_id)

        try:
            messages = await list_messages(
                board_id,
                character_id=char_id,
                unread_only=unread_only,
            )

            if not messages:
                msg = "No new messages." if unread_only else "No messages on this board."
                await ctx.connection.send_line(colorize(msg, "YELLOW"))
                return

            await ctx.connection.send_line("")
            await ctx.connection.send_line(_format_message_list_header())
            await ctx.connection.send_line("-" * 60)

            for msg in messages:
                await ctx.connection.send_line(_format_message_row(msg))

            await ctx.connection.send_line("")
            await ctx.connection.send_line(
                colorize("Type 'read <#>' to read a message.", "DIM")
            )

        except Exception as e:
            logger.error("list_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Failed to list messages.", "RED")
            )


class ReadCommand(Command):
    """Read a message from the current board."""

    name = "read"
    aliases = ["r"]
    help_text = "read [#|new|all] - Read messages"

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the read command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(
                colorize("You must be playing a character.", "RED")
            )
            return

        board_id = _character_board_context.get(ctx.session.character_id)
        if not board_id:
            await ctx.connection.send_line(
                colorize("Select a board first with 'board <name>'.", "YELLOW")
            )
            return

        char_id = UUID(ctx.session.character_id)

        try:
            # Determine which message to read
            target_seq = None

            if not ctx.args:
                # Read next new or current position
                messages = await list_messages(board_id, char_id, unread_only=True, limit=1)
                if messages:
                    target_seq = messages[0].sequence
                else:
                    await ctx.connection.send_line(
                        colorize("No new messages. Use 'read <#>' for a specific message.", "YELLOW")
                    )
                    return
            elif ctx.args[0].lower() == "new":
                messages = await list_messages(board_id, char_id, unread_only=True, limit=1)
                if messages:
                    target_seq = messages[0].sequence
                else:
                    await ctx.connection.send_line(colorize("No new messages.", "YELLOW"))
                    return
            else:
                try:
                    target_seq = int(ctx.args[0])
                except ValueError:
                    await ctx.connection.send_line(
                        colorize("Usage: read <number> or read new", "YELLOW")
                    )
                    return

            # Get the message
            message = await get_message(board_id, target_seq)
            if not message:
                await ctx.connection.send_line(
                    colorize(f"Message #{target_seq} not found.", "RED")
                )
                return

            # Get total count for display
            all_messages = await list_messages(board_id, limit=1000)
            total = len(all_messages)

            # Display message
            for line in _format_message_display(message, target_seq, total):
                await ctx.connection.send_line(line)

            # Mark as read
            await mark_message_read(char_id, message.id)

            # Update position
            _character_message_position[ctx.session.character_id] = target_seq

        except Exception as e:
            logger.error("read_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Failed to read message.", "RED")
            )


class PostCommand(Command):
    """Post a new message to the current board."""

    name = "post"
    aliases = ["write"]
    help_text = "post <subject> - Start a new message"
    min_args = 1

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the post command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(
                colorize("You must be playing a character.", "RED")
            )
            return

        board_id = _character_board_context.get(ctx.session.character_id)
        if not board_id:
            await ctx.connection.send_line(
                colorize("Select a board first with 'board <name>'.", "YELLOW")
            )
            return

        subject = " ".join(ctx.args)

        try:
            async with get_session() as session:
                result = await session.execute(
                    select(Character).where(Character.id == UUID(ctx.session.character_id))
                )
                character = result.scalar_one_or_none()

                if not character:
                    await ctx.connection.send_line(colorize("Character not found.", "RED"))
                    return

                # Check post access
                board = await get_board(board_id)
                if not board:
                    await ctx.connection.send_line(colorize("Board not found.", "RED"))
                    return

                can_post, reason = can_access_board(character, board, for_posting=True)
                if not can_post:
                    await ctx.connection.send_line(colorize(reason, "RED"))
                    return

                # For now, simple single-line body prompt
                # Future enhancement: multi-line editor
                await ctx.connection.send_line(
                    colorize("Enter your message (end with a blank line):", "CYAN")
                )

                body_lines = []
                while True:
                    line = await ctx.connection.readline()
                    if not line or line.strip() == "":
                        break
                    body_lines.append(line)

                if not body_lines:
                    await ctx.connection.send_line(colorize("Message cancelled.", "YELLOW"))
                    return

                body = "\n".join(body_lines)

                success, msg, _ = await post_message(
                    board_id=board_id,
                    author_id=character.id,
                    author_name=character.name,
                    subject=subject,
                    body=body,
                )

                if success:
                    await ctx.connection.send_line(colorize(msg, "GREEN"))
                else:
                    await ctx.connection.send_line(colorize(msg, "RED"))

        except Exception as e:
            logger.error("post_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Failed to post message.", "RED")
            )


class ReplyCommand(Command):
    """Reply to a message on the current board."""

    name = "reply"
    help_text = "reply <#> - Reply to a message"
    min_args = 1

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the reply command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(
                colorize("You must be playing a character.", "RED")
            )
            return

        board_id = _character_board_context.get(ctx.session.character_id)
        if not board_id:
            await ctx.connection.send_line(
                colorize("Select a board first with 'board <name>'.", "YELLOW")
            )
            return

        try:
            parent_seq = int(ctx.args[0])
        except ValueError:
            await ctx.connection.send_line(
                colorize("Usage: reply <message number>", "YELLOW")
            )
            return

        try:
            # Get parent message
            parent = await get_message(board_id, parent_seq)
            if not parent:
                await ctx.connection.send_line(
                    colorize(f"Message #{parent_seq} not found.", "RED")
                )
                return

            async with get_session() as session:
                result = await session.execute(
                    select(Character).where(Character.id == UUID(ctx.session.character_id))
                )
                character = result.scalar_one_or_none()

                if not character:
                    await ctx.connection.send_line(colorize("Character not found.", "RED"))
                    return

                # Check post access
                board = await get_board(board_id)
                if not board:
                    await ctx.connection.send_line(colorize("Board not found.", "RED"))
                    return

                can_post, reason = can_access_board(character, board, for_posting=True)
                if not can_post:
                    await ctx.connection.send_line(colorize(reason, "RED"))
                    return

                # Compose subject
                subject = f"Re: {parent.subject}"
                if len(subject) > 80:
                    subject = subject[:77] + "..."

                await ctx.connection.send_line(
                    colorize(f"Replying to: {parent.subject}", "CYAN")
                )
                await ctx.connection.send_line(
                    colorize("Enter your reply (end with a blank line):", "CYAN")
                )

                body_lines = []
                while True:
                    line = await ctx.connection.readline()
                    if not line or line.strip() == "":
                        break
                    body_lines.append(line)

                if not body_lines:
                    await ctx.connection.send_line(colorize("Reply cancelled.", "YELLOW"))
                    return

                body = "\n".join(body_lines)

                success, msg, _ = await post_message(
                    board_id=board_id,
                    author_id=character.id,
                    author_name=character.name,
                    subject=subject,
                    body=body,
                    reply_to_seq=parent_seq,
                )

                if success:
                    await ctx.connection.send_line(colorize(msg, "GREEN"))
                else:
                    await ctx.connection.send_line(colorize(msg, "RED"))

        except Exception as e:
            logger.error("reply_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Failed to post reply.", "RED")
            )


class RemoveCommand(Command):
    """Remove a message from the current board."""

    name = "remove"
    aliases = ["delete", "rm"]
    help_text = "remove <#> - Remove your own message"
    min_args = 1

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the remove command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(
                colorize("You must be playing a character.", "RED")
            )
            return

        board_id = _character_board_context.get(ctx.session.character_id)
        if not board_id:
            await ctx.connection.send_line(
                colorize("Select a board first with 'board <name>'.", "YELLOW")
            )
            return

        try:
            seq = int(ctx.args[0])
        except ValueError:
            await ctx.connection.send_line(
                colorize("Usage: remove <message number>", "YELLOW")
            )
            return

        try:
            char_id = UUID(ctx.session.character_id)

            # Check if user is moderator (El'the or above)
            async with get_session() as session:
                result = await session.execute(
                    select(Character).where(Character.id == char_id)
                )
                character = result.scalar_one_or_none()

                is_mod = False
                if character:
                    rank = rank_from_string(character.arcanum_rank)
                    is_mod = rank == ArcanumRank.EL_THE

            success, msg = await delete_message(board_id, seq, char_id, is_mod)

            color = "GREEN" if success else "RED"
            await ctx.connection.send_line(colorize(msg, color))

        except Exception as e:
            logger.error("remove_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Failed to remove message.", "RED")
            )


class PinCommand(Command):
    """Pin a message to the top of the board (moderator only)."""

    name = "pin"
    help_text = "pin <#> - Pin message to top (moderators)"
    min_args = 1

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the pin command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(
                colorize("You must be playing a character.", "RED")
            )
            return

        board_id = _character_board_context.get(ctx.session.character_id)
        if not board_id:
            await ctx.connection.send_line(
                colorize("Select a board first with 'board <name>'.", "YELLOW")
            )
            return

        try:
            seq = int(ctx.args[0])
        except ValueError:
            await ctx.connection.send_line(
                colorize("Usage: pin <message number>", "YELLOW")
            )
            return

        try:
            # Check moderator status
            async with get_session() as session:
                result = await session.execute(
                    select(Character).where(Character.id == UUID(ctx.session.character_id))
                )
                character = result.scalar_one_or_none()

                if not character:
                    await ctx.connection.send_line(colorize("Character not found.", "RED"))
                    return

                rank = rank_from_string(character.arcanum_rank)
                if rank != ArcanumRank.EL_THE:
                    await ctx.connection.send_line(
                        colorize("Only El'the may pin messages.", "RED")
                    )
                    return

            success, msg = await pin_message(board_id, seq, pin=True)

            color = "GREEN" if success else "RED"
            await ctx.connection.send_line(colorize(msg, color))

        except Exception as e:
            logger.error("pin_command_failed", error=str(e), exc_info=True)
            await ctx.connection.send_line(
                colorize("Failed to pin message.", "RED")
            )


class NextCommand(Command):
    """Read the next message."""

    name = "next"
    aliases = ["n"]
    help_text = "next - Read next message"

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the next command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(
                colorize("You must be playing a character.", "RED")
            )
            return

        board_id = _character_board_context.get(ctx.session.character_id)
        if not board_id:
            await ctx.connection.send_line(
                colorize("Select a board first with 'board <name>'.", "YELLOW")
            )
            return

        current_pos = _character_message_position.get(ctx.session.character_id, 0)
        next_pos = current_pos + 1

        # Delegate to read command
        ctx.args = [str(next_pos)]
        read_cmd = ReadCommand()
        await read_cmd.execute(ctx)


class PrevCommand(Command):
    """Read the previous message."""

    name = "prev"
    aliases = ["p", "previous"]
    help_text = "prev - Read previous message"

    async def execute(self, ctx: CommandContext) -> None:
        """Execute the prev command."""
        if not ctx.session.character_id:
            await ctx.connection.send_line(
                colorize("You must be playing a character.", "RED")
            )
            return

        board_id = _character_board_context.get(ctx.session.character_id)
        if not board_id:
            await ctx.connection.send_line(
                colorize("Select a board first with 'board <name>'.", "YELLOW")
            )
            return

        current_pos = _character_message_position.get(ctx.session.character_id, 2)
        prev_pos = max(1, current_pos - 1)

        # Delegate to read command
        ctx.args = [str(prev_pos)]
        read_cmd = ReadCommand()
        await read_cmd.execute(ctx)
```

---

## File Structure

```
src/waystone/
├── database/
│   └── models/
│       └── bulletin.py          # NEW: BulletinBoard, BoardMessage, MessageRead
│
├── game/
│   ├── commands/
│   │   └── board.py             # NEW: All BBS commands
│   │
│   └── systems/
│       ├── bulletin.py          # NEW: Board management system
│       └── npc_poster.py        # NEW: NPC posting system
│
└── tests/
    └── game/
        └── systems/
            └── test_bulletin.py # NEW: BBS system tests
```

---

## Implementation Plan

### Phase 1: Core Foundation (Days 1-2)
1. Create `bulletin.py` database models
2. Add models to `__init__.py` exports
3. Run database migration (alembic or recreate)
4. Create `bulletin.py` game system with basic CRUD
5. Write unit tests for models and system functions

### Phase 2: Commands (Days 3-4)
1. Create `board.py` command file
2. Implement BoardCommand, ListCommand, ReadCommand
3. Implement PostCommand, ReplyCommand
4. Implement RemoveCommand, PinCommand
5. Implement navigation commands (Next, Prev)
6. Register commands in GameEngine._register_commands()
7. Integration tests for command flow

### Phase 3: NPC Integration (Days 5-6)
1. Create `npc_poster.py` system
2. Define NPC personality templates
3. Create posting schedules
4. Integrate check_npc_posts() into periodic cleanup task
5. Test NPC posting behavior

### Phase 4: Polish (Day 7)
1. Add board initialization to GameEngine.start()
2. Add "board" keyword to room examine output
3. Test access control scenarios
4. Load testing for many messages
5. Documentation updates

---

## Testing Strategy

### Unit Tests

```python
# tests/game/systems/test_bulletin.py

import pytest
from uuid import uuid4
from datetime import datetime, UTC

from waystone.database.models.bulletin import (
    BulletinBoard,
    BoardMessage,
    MessageRead,
    BoardAccessLevel,
)
from waystone.game.systems.bulletin import (
    can_access_board,
    post_message,
    list_messages,
    get_message,
    mark_message_read,
)


class TestBulletinModels:
    """Tests for bulletin board database models."""

    def test_board_creation(self):
        """Test creating a bulletin board."""
        board = BulletinBoard(
            id="test_board",
            name="Test Board",
            description="A test board",
            room_id="test_room",
        )
        assert board.id == "test_board"
        assert board.read_level == BoardAccessLevel.PUBLIC
        assert board.max_messages == 50

    def test_message_creation(self):
        """Test creating a board message."""
        msg = BoardMessage(
            board_id="test_board",
            author_name="Test User",
            subject="Test Subject",
            body="Test body content",
            board_sequence=1,
        )
        assert msg.subject == "Test Subject"
        assert msg.is_pinned is False
        assert msg.is_anonymous is False


class TestAccessControl:
    """Tests for board access control."""

    @pytest.fixture
    def public_board(self):
        return BulletinBoard(
            id="public",
            name="Public Board",
            description="",
            room_id="room",
            read_level=BoardAccessLevel.PUBLIC,
            post_level=BoardAccessLevel.PUBLIC,
        )

    @pytest.fixture
    def student_board(self):
        return BulletinBoard(
            id="student",
            name="Student Board",
            description="",
            room_id="room",
            read_level=BoardAccessLevel.STUDENT,
            post_level=BoardAccessLevel.ADVANCED,
        )

    def test_public_access(self, public_board, mock_character):
        """Anyone can access public board."""
        mock_character.arcanum_rank = "none"
        can_read, _ = can_access_board(mock_character, public_board, for_posting=False)
        assert can_read is True

    def test_rank_required(self, student_board, mock_character):
        """Student board requires E'lir rank."""
        mock_character.arcanum_rank = "none"
        can_read, reason = can_access_board(mock_character, student_board, for_posting=False)
        assert can_read is False
        assert "rank" in reason.lower()

        mock_character.arcanum_rank = "e_lir"
        can_read, _ = can_access_board(mock_character, student_board, for_posting=False)
        assert can_read is True


class TestMessageOperations:
    """Tests for message CRUD operations."""

    @pytest.mark.asyncio
    async def test_post_message(self, db_session, test_board):
        """Test posting a new message."""
        success, msg, message = await post_message(
            board_id=test_board.id,
            author_id=uuid4(),
            author_name="Test Author",
            subject="Test Post",
            body="This is a test message.",
        )

        assert success is True
        assert message is not None
        assert message.board_sequence == 1

    @pytest.mark.asyncio
    async def test_list_messages(self, db_session, test_board_with_messages):
        """Test listing messages."""
        messages = await list_messages(test_board_with_messages.id)

        assert len(messages) > 0
        assert all(m.board_id == test_board_with_messages.id for m in messages)

    @pytest.mark.asyncio
    async def test_mark_read(self, db_session, test_message):
        """Test marking a message as read."""
        char_id = uuid4()

        await mark_message_read(char_id, test_message.id)

        # Should be idempotent
        await mark_message_read(char_id, test_message.id)
```

### Integration Tests

```python
# tests/game/commands/test_board_commands.py

import pytest
from waystone.game.commands.board import (
    BoardCommand,
    ListCommand,
    ReadCommand,
    PostCommand,
)


class TestBoardCommands:
    """Integration tests for board commands."""

    @pytest.mark.asyncio
    async def test_board_list_in_room(self, game_ctx, character_in_university):
        """Test listing boards in university courtyard."""
        cmd = BoardCommand()
        await cmd.execute(game_ctx)

        # Check output contains board names
        output = game_ctx.connection.get_output()
        assert "University Notice Board" in output

    @pytest.mark.asyncio
    async def test_select_board(self, game_ctx, character_in_university):
        """Test selecting a board."""
        game_ctx.args = ["notice"]

        cmd = BoardCommand()
        await cmd.execute(game_ctx)

        output = game_ctx.connection.get_output()
        assert "UNIVERSITY NOTICE BOARD" in output

    @pytest.mark.asyncio
    async def test_post_and_read_flow(self, game_ctx, character_in_university):
        """Test full post and read flow."""
        # Select board
        game_ctx.args = ["notice"]
        await BoardCommand().execute(game_ctx)

        # Post message
        game_ctx.args = ["Test Subject"]
        game_ctx.connection.set_input_queue(["Test body line 1", "Test body line 2", ""])
        await PostCommand().execute(game_ctx)

        output = game_ctx.connection.get_output()
        assert "posted" in output.lower()

        # Read message
        game_ctx.args = ["1"]
        await ReadCommand().execute(game_ctx)

        output = game_ctx.connection.get_output()
        assert "Test Subject" in output
        assert "Test body line 1" in output
```

---

## Risk Assessment

### Technical Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Database migration issues | Medium | High | Test migrations on copy first |
| Performance with many messages | Low | Medium | Index on board_id, created_at |
| NPC posting too frequently | Medium | Low | Configurable intervals, probability |
| Session state lost on disconnect | High | Low | Boards in room, re-select needed |

### Design Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Access control too restrictive | Medium | Medium | Start permissive, tighten later |
| NPC content repetitive | Medium | Medium | Large template pool, variables |
| Threading confusing to users | Low | Low | Simple flat threading, clear UI |

---

## Future Enhancements

1. **Private Messaging**: Direct messages between characters
2. **Board Subscriptions**: Notifications when boards update
3. **Search Capability**: Search messages by author, subject, content
4. **Archive System**: Old messages moved to archives instead of deleted
5. **Moderation Queue**: Review anonymous posts before publication
6. **Cross-Room Access**: Sympathetically linked boards (premium feature)
7. **Rich Formatting**: Support for in-game markup in messages

---

## Conclusion

This architecture provides a solid foundation for a vintage BBS-style bulletin board system that integrates seamlessly with the existing Waystone MUD codebase. The design follows established patterns (SQLAlchemy models, Command pattern, game systems) while adding thematic NPC content that brings the Kingkiller Chronicle world to life.

The phased implementation approach minimizes risk by delivering core functionality first, with NPC integration and polish following. The testing strategy ensures reliability, and the modular design allows for future enhancements without major refactoring.
