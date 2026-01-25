"""Bulletin Board System manager for Waystone MUD.

Handles:
- Board access control based on Arcanum rank
- Message CRUD operations
- Read tracking per character
- Message pruning
- ANSI-style formatting for display
"""

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from waystone.database.models.bulletin import (
    BoardAccessLevel,
    BoardMessage,
    BulletinBoard,
    MessageRead,
)
from waystone.game.systems.university import ArcanumRank, rank_from_string

if TYPE_CHECKING:
    from waystone.database.models import Character

logger = structlog.get_logger(__name__)


@dataclass
class BoardInfo:
    """Lightweight board data transfer object."""

    id: str
    name: str
    description: str
    room_id: str
    read_level: BoardAccessLevel
    post_level: BoardAccessLevel
    max_messages: int
    allow_anonymous: bool
    is_active: bool
    message_count: int = 0
    unread_count: int = 0


@dataclass
class MessageInfo:
    """Message display data with read status."""

    id: uuid.UUID
    board_id: str
    author_name: str
    subject: str
    body: str
    board_sequence: int
    is_pinned: bool
    is_anonymous: bool
    is_read: bool
    created_at: datetime
    reply_to: uuid.UUID | None
    reply_to_sequence: int | None


# Access level hierarchy mapping
ACCESS_LEVEL_RANK_MAP = {
    BoardAccessLevel.PUBLIC: ArcanumRank.NONE,
    BoardAccessLevel.STUDENT: ArcanumRank.E_LIR,
    BoardAccessLevel.ADVANCED: ArcanumRank.RE_LAR,
    BoardAccessLevel.MASTER: ArcanumRank.EL_THE,
    BoardAccessLevel.PRIVATE: ArcanumRank.EL_THE,  # Private requires explicit whitelist
}

RANK_ORDER = [ArcanumRank.NONE, ArcanumRank.E_LIR, ArcanumRank.RE_LAR, ArcanumRank.EL_THE]


class BoardManager:
    """Main system manager for bulletin boards."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize BoardManager with database session."""
        self._session = session

    async def get_boards_in_room(self, room_id: str) -> list[BoardInfo]:
        """Get all active boards in a specific room."""
        result = await self._session.execute(
            select(BulletinBoard)
            .where(
                and_(
                    BulletinBoard.room_id == room_id,
                    BulletinBoard.is_active == True,  # noqa: E712
                )
            )
            .order_by(BulletinBoard.name)
        )
        boards = result.scalars().all()

        board_infos = []
        for board in boards:
            # Count messages
            msg_count_result = await self._session.execute(
                select(func.count()).select_from(BoardMessage).where(BoardMessage.board_id == board.id)
            )
            message_count = msg_count_result.scalar() or 0

            board_infos.append(
                BoardInfo(
                    id=board.id,
                    name=board.name,
                    description=board.description,
                    room_id=board.room_id,
                    read_level=board.read_level,
                    post_level=board.post_level,
                    max_messages=board.max_messages,
                    allow_anonymous=board.allow_anonymous,
                    is_active=board.is_active,
                    message_count=message_count,
                    unread_count=0,  # Requires character_id to calculate
                )
            )

        return board_infos

    async def get_board_by_id(self, board_id: str) -> BoardInfo | None:
        """Get a board by its ID."""
        result = await self._session.execute(
            select(BulletinBoard).where(BulletinBoard.id == board_id)
        )
        board = result.scalar_one_or_none()

        if not board:
            return None

        # Count messages
        msg_count_result = await self._session.execute(
            select(func.count()).select_from(BoardMessage).where(BoardMessage.board_id == board.id)
        )
        message_count = msg_count_result.scalar() or 0

        return BoardInfo(
            id=board.id,
            name=board.name,
            description=board.description,
            room_id=board.room_id,
            read_level=board.read_level,
            post_level=board.post_level,
            max_messages=board.max_messages,
            allow_anonymous=board.allow_anonymous,
            is_active=board.is_active,
            message_count=message_count,
            unread_count=0,
        )

    async def can_read_board(self, character: "Character", board: BulletinBoard) -> bool:
        """Check if character can read a board."""
        return self._check_access_level(character, board.read_level)

    async def can_post_to_board(self, character: "Character", board: BulletinBoard) -> bool:
        """Check if character can post to a board."""
        # First check rank requirement
        if not self._check_access_level(character, board.post_level):
            return False

        # Then check attribute requirements if any
        if board.attribute_requirement:
            if not self._check_attribute_requirement(character, board.attribute_requirement):
                return False

        return True

    def _check_access_level(self, character: "Character", required_level: BoardAccessLevel) -> bool:
        """Check if character meets the access level requirement."""
        if required_level == BoardAccessLevel.PUBLIC:
            return True

        if required_level == BoardAccessLevel.PRIVATE:
            # Private boards need explicit whitelist logic
            return False

        required_rank = ACCESS_LEVEL_RANK_MAP.get(required_level, ArcanumRank.NONE)
        character_rank = rank_from_string(character.arcanum_rank)

        # Check if character's rank is sufficient
        required_idx = RANK_ORDER.index(required_rank)
        character_idx = RANK_ORDER.index(character_rank)

        return character_idx >= required_idx

    def _check_attribute_requirement(self, character: "Character", requirements_json: str) -> bool:
        """Check if character meets attribute requirements."""
        try:
            requirements = json.loads(requirements_json)
        except (json.JSONDecodeError, TypeError):
            return True  # Invalid JSON means no restriction

        for attr_name, required_value in requirements.items():
            attr_name_lower = attr_name.lower()
            character_value = getattr(character, attr_name_lower, 0)
            if character_value < required_value:
                return False

        return True

    async def get_messages(
        self, board_id: str, character_id: uuid.UUID, limit: int = 50
    ) -> list[MessageInfo]:
        """Get messages from a board with read status for character."""
        result = await self._session.execute(
            select(BoardMessage)
            .where(BoardMessage.board_id == board_id)
            .order_by(BoardMessage.is_pinned.desc(), BoardMessage.board_sequence)
            .limit(limit)
        )
        messages = result.scalars().all()

        # Get read status for all messages
        read_result = await self._session.execute(
            select(MessageRead.message_id).where(
                and_(
                    MessageRead.character_id == character_id,
                    MessageRead.message_id.in_([m.id for m in messages]),
                )
            )
        )
        read_ids = set(read_result.scalars().all())

        message_infos = []
        for msg in messages:
            # Get reply_to_sequence if this is a reply
            reply_to_sequence = None
            if msg.reply_to:
                parent_result = await self._session.execute(
                    select(BoardMessage.board_sequence).where(BoardMessage.id == msg.reply_to)
                )
                reply_to_sequence = parent_result.scalar_one_or_none()

            message_infos.append(
                MessageInfo(
                    id=msg.id,
                    board_id=msg.board_id,
                    author_name=msg.author_name,
                    subject=msg.subject,
                    body=msg.body,
                    board_sequence=msg.board_sequence,
                    is_pinned=msg.is_pinned,
                    is_anonymous=msg.is_anonymous,
                    is_read=msg.id in read_ids,
                    created_at=msg.created_at,
                    reply_to=msg.reply_to,
                    reply_to_sequence=reply_to_sequence,
                )
            )

        return message_infos

    async def get_unread_count(self, board_id: str, character_id: uuid.UUID) -> int:
        """Get count of unread messages on a board for a character."""
        # Get all message IDs on this board
        all_messages = await self._session.execute(
            select(BoardMessage.id).where(BoardMessage.board_id == board_id)
        )
        all_message_ids = set(all_messages.scalars().all())

        if not all_message_ids:
            return 0

        # Get read message IDs for this character
        read_result = await self._session.execute(
            select(MessageRead.message_id).where(
                and_(
                    MessageRead.character_id == character_id,
                    MessageRead.message_id.in_(all_message_ids),
                )
            )
        )
        read_ids = set(read_result.scalars().all())

        return len(all_message_ids - read_ids)

    async def get_message_by_sequence(
        self, board_id: str, sequence: int
    ) -> MessageInfo | None:
        """Get a specific message by its sequence number."""
        result = await self._session.execute(
            select(BoardMessage).where(
                and_(
                    BoardMessage.board_id == board_id,
                    BoardMessage.board_sequence == sequence,
                )
            )
        )
        msg = result.scalar_one_or_none()

        if not msg:
            return None

        # Get reply_to_sequence if this is a reply
        reply_to_sequence = None
        if msg.reply_to:
            parent_result = await self._session.execute(
                select(BoardMessage.board_sequence).where(BoardMessage.id == msg.reply_to)
            )
            reply_to_sequence = parent_result.scalar_one_or_none()

        return MessageInfo(
            id=msg.id,
            board_id=msg.board_id,
            author_name=msg.author_name,
            subject=msg.subject,
            body=msg.body,
            board_sequence=msg.board_sequence,
            is_pinned=msg.is_pinned,
            is_anonymous=msg.is_anonymous,
            is_read=False,  # Unknown without character_id
            created_at=msg.created_at,
            reply_to=msg.reply_to,
            reply_to_sequence=reply_to_sequence,
        )

    async def post_message(
        self,
        board_id: str,
        author_id: uuid.UUID,
        subject: str,
        body: str,
        reply_to: int | None = None,
        is_anonymous: bool = False,
    ) -> MessageInfo:
        """Post a new message to a board."""
        from waystone.database.models import Character

        # Get author name
        author_result = await self._session.execute(
            select(Character).where(Character.id == author_id)
        )
        author = author_result.scalar_one()

        # Get next sequence number
        seq_result = await self._session.execute(
            select(func.max(BoardMessage.board_sequence)).where(BoardMessage.board_id == board_id)
        )
        max_seq = seq_result.scalar() or 0
        next_seq = max_seq + 1

        # Get reply_to message ID if replying
        reply_to_id = None
        if reply_to:
            reply_result = await self._session.execute(
                select(BoardMessage.id).where(
                    and_(
                        BoardMessage.board_id == board_id,
                        BoardMessage.board_sequence == reply_to,
                    )
                )
            )
            reply_to_id = reply_result.scalar_one_or_none()

        # Create the message
        message = BoardMessage(
            board_id=board_id,
            author_id=author_id,
            author_name=author.name,
            subject=subject,
            body=body,
            board_sequence=next_seq,
            is_pinned=False,
            is_anonymous=is_anonymous,
            reply_to=reply_to_id,
        )

        self._session.add(message)
        await self._session.commit()
        await self._session.refresh(message)

        logger.info(
            "message_posted",
            board_id=board_id,
            author_id=str(author_id),
            message_id=str(message.id),
            sequence=next_seq,
        )

        return MessageInfo(
            id=message.id,
            board_id=message.board_id,
            author_name=message.author_name,
            subject=message.subject,
            body=message.body,
            board_sequence=message.board_sequence,
            is_pinned=message.is_pinned,
            is_anonymous=message.is_anonymous,
            is_read=True,  # Author has read their own message
            created_at=message.created_at,
            reply_to=message.reply_to,
            reply_to_sequence=reply_to,
        )

    async def delete_message(
        self, message_id: uuid.UUID, character_id: uuid.UUID
    ) -> bool:
        """Delete a message. Returns True if deleted, False if denied."""
        from waystone.database.models import Character

        result = await self._session.execute(
            select(BoardMessage).where(BoardMessage.id == message_id)
        )
        message = result.scalar_one_or_none()

        if not message:
            return False

        # Check if character is the author
        if message.author_id == character_id:
            await self._session.delete(message)
            await self._session.commit()
            logger.info(
                "message_deleted",
                message_id=str(message_id),
                deleted_by=str(character_id),
            )
            return True

        # Check if character is a moderator (El'the or Master)
        char_result = await self._session.execute(
            select(Character).where(Character.id == character_id)
        )
        character = char_result.scalar_one_or_none()

        if character:
            char_rank = rank_from_string(character.arcanum_rank)
            if char_rank == ArcanumRank.EL_THE:
                await self._session.delete(message)
                await self._session.commit()
                logger.info(
                    "message_deleted_by_moderator",
                    message_id=str(message_id),
                    moderator_id=str(character_id),
                )
                return True

        return False

    async def pin_message(
        self, message_id: uuid.UUID, character_id: uuid.UUID
    ) -> bool:
        """Pin a message. Only El'the or Master can pin."""
        from waystone.database.models import Character

        # Check if character is a moderator
        char_result = await self._session.execute(
            select(Character).where(Character.id == character_id)
        )
        character = char_result.scalar_one_or_none()

        if not character:
            return False

        char_rank = rank_from_string(character.arcanum_rank)
        if char_rank != ArcanumRank.EL_THE:
            return False

        # Pin the message
        result = await self._session.execute(
            select(BoardMessage).where(BoardMessage.id == message_id)
        )
        message = result.scalar_one_or_none()

        if not message:
            return False

        message.is_pinned = True
        await self._session.commit()

        logger.info(
            "message_pinned",
            message_id=str(message_id),
            pinned_by=str(character_id),
        )

        return True

    async def mark_as_read(
        self, message_id: uuid.UUID, character_id: uuid.UUID
    ) -> None:
        """Mark a message as read for a character."""
        # Check if already read
        existing = await self._session.execute(
            select(MessageRead).where(
                and_(
                    MessageRead.character_id == character_id,
                    MessageRead.message_id == message_id,
                )
            )
        )

        if existing.scalar_one_or_none():
            return  # Already read

        read_record = MessageRead(
            character_id=character_id,
            message_id=message_id,
        )
        self._session.add(read_record)
        await self._session.commit()

    async def prune_old_messages(self, board_id: str) -> int:
        """Prune old messages when board exceeds max_messages. Returns count pruned."""
        # Get board info
        board_result = await self._session.execute(
            select(BulletinBoard).where(BulletinBoard.id == board_id)
        )
        board = board_result.scalar_one_or_none()

        if not board:
            return 0

        # Count current messages
        count_result = await self._session.execute(
            select(func.count()).select_from(BoardMessage).where(BoardMessage.board_id == board_id)
        )
        current_count = count_result.scalar() or 0

        if current_count <= board.max_messages:
            return 0

        to_prune = current_count - board.max_messages

        # Get oldest non-pinned messages to delete
        oldest_result = await self._session.execute(
            select(BoardMessage.id)
            .where(
                and_(
                    BoardMessage.board_id == board_id,
                    BoardMessage.is_pinned == False,  # noqa: E712
                )
            )
            .order_by(BoardMessage.created_at)
            .limit(to_prune)
        )
        ids_to_delete = list(oldest_result.scalars().all())

        if ids_to_delete:
            await self._session.execute(
                delete(BoardMessage).where(BoardMessage.id.in_(ids_to_delete))
            )
            await self._session.commit()

            logger.info(
                "messages_pruned",
                board_id=board_id,
                count=len(ids_to_delete),
            )

        return len(ids_to_delete)


class MessageFormatter:
    """Static methods for formatting board and message output."""

    @staticmethod
    def format_board_list(boards: list[BoardInfo], character: "Character | None" = None) -> str:
        """Format a list of boards for display."""
        # character parameter reserved for future personalization features
        _ = character
        if not boards:
            return "There are no bulletin boards here."

        lines = []
        lines.append("Available Bulletin Boards:")
        lines.append("-" * 60)

        for board in boards:
            unread_tag = ""
            if board.unread_count > 0:
                unread_tag = f" [NEW: {board.unread_count}]"

            lines.append(f"  {board.name}{unread_tag}")
            lines.append(f"    {board.description}")
            lines.append(f"    ({board.message_count} messages)")
            lines.append("")

        lines.append("Use 'board <name>' to select a board.")

        return "\n".join(lines)

    @staticmethod
    def format_message_list(messages: list[MessageInfo], character: "Character | None" = None) -> str:
        """Format a list of messages for display."""
        # character parameter reserved for future personalization features
        _ = character
        if not messages:
            return "No messages on this board."

        lines = []
        lines.append(" #   Date       From             Subject")
        lines.append("-" * 60)

        for msg in messages:
            # Format date
            date_str = msg.created_at.strftime("%m/%d")

            # Format author
            author = "Anonymous" if msg.is_anonymous else msg.author_name
            author = author[:16].ljust(16)

            # Format subject with tags
            subject = msg.subject[:30]
            if msg.is_pinned:
                subject = f"[PINNED] {subject}"
            if not msg.is_read:
                subject = f"[NEW] {subject}"

            # Reply indicator
            if msg.reply_to_sequence:
                subject = f"Re #{msg.reply_to_sequence}: {subject}"

            line = f"{msg.board_sequence:3d}  {date_str}  {author}  {subject}"
            lines.append(line)

        return "\n".join(lines)

    @staticmethod
    def format_message(
        message: MessageInfo, character: "Character | None" = None, total_messages: int = 0
    ) -> str:
        """Format a single message with ANSI-style borders."""
        # character parameter reserved for future personalization features
        _ = character
        # Box drawing characters
        top_left = ""
        top_right = ""
        bottom_left = ""
        bottom_right = ""
        horizontal = ""
        vertical = ""
        left_tee = ""
        right_tee = ""

        width = 60

        # Build the formatted message
        lines = []

        # Top border
        lines.append(top_left + horizontal * (width - 2) + top_right)

        # Message number
        if total_messages > 0:
            header = f" Message #{message.board_sequence} of {total_messages}"
        else:
            header = f" Message #{message.board_sequence}"
        header = header.ljust(width - 2)
        lines.append(vertical + header + vertical)

        # Separator
        lines.append(left_tee + horizontal * (width - 2) + right_tee)

        # Author
        author = "Anonymous" if message.is_anonymous else message.author_name
        author_line = f" From: {author}".ljust(width - 2)
        lines.append(vertical + author_line + vertical)

        # Date - format in-world style
        date_str = message.created_at.strftime("%A, %B %d")
        date_line = f" Date: {date_str}".ljust(width - 2)
        lines.append(vertical + date_line + vertical)

        # Subject
        subject_line = f" Subj: {message.subject}".ljust(width - 2)
        lines.append(vertical + subject_line + vertical)

        # Bottom border of header
        lines.append(bottom_left + horizontal * (width - 2) + bottom_right)

        # Message body
        lines.append("")
        for body_line in message.body.split("\n"):
            lines.append(body_line)
        lines.append("")

        # Reply indicator
        if message.reply_to_sequence:
            lines.append(f"(In reply to message #{message.reply_to_sequence})")

        return "\n".join(lines)

    @staticmethod
    def format_board_header(board: BoardInfo, unread_count: int) -> str:
        """Format a board header with info."""
        lines = []
        lines.append(f"=== {board.name} ===")
        lines.append(board.description)
        if unread_count > 0:
            lines.append(f"You have {unread_count} unread message(s).")
        lines.append(f"Total: {board.message_count} messages")
        lines.append("")
        return "\n".join(lines)
