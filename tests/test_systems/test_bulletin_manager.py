"""Tests for Bulletin Board System BoardManager.

These tests verify:
- Access control with different Arcanum ranks
- Message CRUD operations
- Read tracking
- Message pruning
- Attribute requirements
- Message formatting
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from waystone.database.models import Base, Character, CharacterBackground, User
from waystone.database.models.bulletin import (
    BoardAccessLevel,
    BulletinBoard,
)
from waystone.game.systems.bulletin import (
    BoardInfo,
    BoardManager,
    MessageFormatter,
    MessageInfo,
)


@pytest.fixture
async def db_session():
    """Create a test database session with in-memory SQLite."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys=ON"))
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        await session.execute(text("PRAGMA foreign_keys=ON"))
        yield session
        await session.rollback()

    await engine.dispose()


@pytest.fixture
async def sample_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(
        username="testuser",
        email="test@example.com",
        password_hash=User.hash_password("password123"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def sample_character(db_session: AsyncSession, sample_user: User) -> Character:
    """Create a test character with E'lir rank."""
    character = Character(
        user_id=sample_user.id,
        name="TestScholar",
        background=CharacterBackground.SCHOLAR,
        current_room_id="university_courtyard",
        arcanum_rank="e_lir",
        charisma=14,
    )
    db_session.add(character)
    await db_session.commit()
    await db_session.refresh(character)
    return character


@pytest.fixture
async def non_student_character(db_session: AsyncSession, sample_user: User) -> Character:
    """Create a character without University rank."""
    character = Character(
        user_id=sample_user.id,
        name="Commoner",
        background=CharacterBackground.COMMONER,
        current_room_id="imre_main_square",
        arcanum_rank="none",
        charisma=8,
    )
    db_session.add(character)
    await db_session.commit()
    await db_session.refresh(character)
    return character


@pytest.fixture
async def advanced_character(db_session: AsyncSession, sample_user: User) -> Character:
    """Create a Re'lar character."""
    character = Character(
        user_id=sample_user.id,
        name="AdvancedScholar",
        background=CharacterBackground.SCHOLAR,
        current_room_id="university_courtyard",
        arcanum_rank="re_lar",
        charisma=12,
    )
    db_session.add(character)
    await db_session.commit()
    await db_session.refresh(character)
    return character


@pytest.fixture
async def master_character(db_session: AsyncSession, sample_user: User) -> Character:
    """Create an El'the character."""
    character = Character(
        user_id=sample_user.id,
        name="MasterScholar",
        background=CharacterBackground.SCHOLAR,
        current_room_id="university_courtyard",
        arcanum_rank="el_the",
        charisma=16,
    )
    db_session.add(character)
    await db_session.commit()
    await db_session.refresh(character)
    return character


@pytest.fixture
async def public_board(db_session: AsyncSession) -> BulletinBoard:
    """Create a public bulletin board."""
    board = BulletinBoard(
        id="imre_marketplace",
        name="Imre Marketplace",
        description="Buy, sell, and trade goods.",
        room_id="imre_main_square",
        read_level=BoardAccessLevel.PUBLIC,
        post_level=BoardAccessLevel.PUBLIC,
        max_messages=50,
        allow_anonymous=True,
        is_active=True,
    )
    db_session.add(board)
    await db_session.commit()
    await db_session.refresh(board)
    return board


@pytest.fixture
async def student_board(db_session: AsyncSession) -> BulletinBoard:
    """Create a student-only bulletin board."""
    board = BulletinBoard(
        id="university_main",
        name="University Notice Board",
        description="Official notices for University members.",
        room_id="university_courtyard",
        read_level=BoardAccessLevel.PUBLIC,
        post_level=BoardAccessLevel.STUDENT,
        max_messages=50,
        allow_anonymous=False,
        is_active=True,
    )
    db_session.add(board)
    await db_session.commit()
    await db_session.refresh(board)
    return board


@pytest.fixture
async def advanced_board(db_session: AsyncSession) -> BulletinBoard:
    """Create an advanced research board."""
    board = BulletinBoard(
        id="archives_research",
        name="Research Requests",
        description="Advanced research discussion.",
        room_id="university_archives",
        read_level=BoardAccessLevel.STUDENT,
        post_level=BoardAccessLevel.ADVANCED,
        max_messages=30,
        allow_anonymous=False,
        is_active=True,
    )
    db_session.add(board)
    await db_session.commit()
    await db_session.refresh(board)
    return board


@pytest.fixture
async def charisma_board(db_session: AsyncSession) -> BulletinBoard:
    """Create a board with charisma requirement."""
    board = BulletinBoard(
        id="eolian_performers",
        name="Eolian Performance Board",
        description="For musicians and performers.",
        room_id="imre_eolian",
        read_level=BoardAccessLevel.PUBLIC,
        post_level=BoardAccessLevel.PUBLIC,
        max_messages=50,
        allow_anonymous=False,
        is_active=True,
        attribute_requirement='{"charisma": 12}',
    )
    db_session.add(board)
    await db_session.commit()
    await db_session.refresh(board)
    return board


@pytest.fixture
def board_manager(db_session: AsyncSession) -> BoardManager:
    """Create a BoardManager instance."""
    return BoardManager(db_session)


class TestBoardInfo:
    """Tests for BoardInfo dataclass."""

    def test_board_info_creation(self):
        """Test creating a BoardInfo."""
        info = BoardInfo(
            id="test_board",
            name="Test Board",
            description="A test board.",
            room_id="test_room",
            read_level=BoardAccessLevel.PUBLIC,
            post_level=BoardAccessLevel.STUDENT,
            max_messages=50,
            allow_anonymous=False,
            is_active=True,
            message_count=10,
            unread_count=3,
        )
        assert info.id == "test_board"
        assert info.name == "Test Board"
        assert info.message_count == 10
        assert info.unread_count == 3


class TestMessageInfo:
    """Tests for MessageInfo dataclass."""

    def test_message_info_creation(self):
        """Test creating a MessageInfo."""
        msg_id = uuid.uuid4()
        now = datetime.now(UTC)
        info = MessageInfo(
            id=msg_id,
            board_id="test_board",
            author_name="TestAuthor",
            subject="Test Subject",
            body="Test body content.",
            board_sequence=1,
            is_pinned=False,
            is_anonymous=False,
            is_read=True,
            created_at=now,
            reply_to=None,
            reply_to_sequence=None,
        )
        assert info.id == msg_id
        assert info.author_name == "TestAuthor"
        assert info.is_read is True


class TestBoardManagerAccessControl:
    """Tests for BoardManager access control."""

    async def test_public_board_read_access_for_anyone(
        self,
        board_manager: BoardManager,
        public_board: BulletinBoard,
        non_student_character: Character,
    ):
        """Test that anyone can read public boards."""
        can_read = await board_manager.can_read_board(non_student_character, public_board)
        assert can_read is True

    async def test_public_board_post_access_for_anyone(
        self,
        board_manager: BoardManager,
        public_board: BulletinBoard,
        non_student_character: Character,
    ):
        """Test that anyone can post to public boards."""
        can_post = await board_manager.can_post_to_board(non_student_character, public_board)
        assert can_post is True

    async def test_student_board_post_denied_for_non_student(
        self,
        board_manager: BoardManager,
        student_board: BulletinBoard,
        non_student_character: Character,
    ):
        """Test that non-students cannot post to student boards."""
        can_post = await board_manager.can_post_to_board(non_student_character, student_board)
        assert can_post is False

    async def test_student_board_post_allowed_for_elir(
        self, board_manager: BoardManager, student_board: BulletinBoard, sample_character: Character
    ):
        """Test that E'lir can post to student boards."""
        can_post = await board_manager.can_post_to_board(sample_character, student_board)
        assert can_post is True

    async def test_advanced_board_read_denied_for_non_student(
        self,
        board_manager: BoardManager,
        advanced_board: BulletinBoard,
        non_student_character: Character,
    ):
        """Test that non-students cannot read advanced boards."""
        can_read = await board_manager.can_read_board(non_student_character, advanced_board)
        assert can_read is False

    async def test_advanced_board_read_allowed_for_elir(
        self,
        board_manager: BoardManager,
        advanced_board: BulletinBoard,
        sample_character: Character,
    ):
        """Test that E'lir can read advanced boards (STUDENT read level)."""
        can_read = await board_manager.can_read_board(sample_character, advanced_board)
        assert can_read is True

    async def test_advanced_board_post_denied_for_elir(
        self,
        board_manager: BoardManager,
        advanced_board: BulletinBoard,
        sample_character: Character,
    ):
        """Test that E'lir cannot post to advanced boards (ADVANCED post level)."""
        can_post = await board_manager.can_post_to_board(sample_character, advanced_board)
        assert can_post is False

    async def test_advanced_board_post_allowed_for_relar(
        self,
        board_manager: BoardManager,
        advanced_board: BulletinBoard,
        advanced_character: Character,
    ):
        """Test that Re'lar can post to advanced boards."""
        can_post = await board_manager.can_post_to_board(advanced_character, advanced_board)
        assert can_post is True

    async def test_charisma_requirement_met(
        self,
        board_manager: BoardManager,
        charisma_board: BulletinBoard,
        sample_character: Character,
    ):
        """Test posting allowed when charisma requirement is met."""
        # sample_character has charisma 14, requirement is 12
        can_post = await board_manager.can_post_to_board(sample_character, charisma_board)
        assert can_post is True

    async def test_charisma_requirement_not_met(
        self,
        board_manager: BoardManager,
        charisma_board: BulletinBoard,
        non_student_character: Character,
    ):
        """Test posting denied when charisma requirement is not met."""
        # non_student_character has charisma 8, requirement is 12
        can_post = await board_manager.can_post_to_board(non_student_character, charisma_board)
        assert can_post is False


class TestBoardManagerCRUD:
    """Tests for BoardManager CRUD operations."""

    async def test_get_boards_in_room(
        self, board_manager: BoardManager, student_board: BulletinBoard, db_session: AsyncSession
    ):
        """Test retrieving boards in a specific room."""
        boards = await board_manager.get_boards_in_room("university_courtyard")
        assert len(boards) == 1
        assert boards[0].id == "university_main"

    async def test_get_boards_in_room_empty(self, board_manager: BoardManager):
        """Test retrieving boards from room with no boards."""
        boards = await board_manager.get_boards_in_room("nonexistent_room")
        assert len(boards) == 0

    async def test_get_board_by_id(self, board_manager: BoardManager, student_board: BulletinBoard):
        """Test retrieving a board by ID."""
        board_info = await board_manager.get_board_by_id("university_main")
        assert board_info is not None
        assert board_info.id == "university_main"
        assert board_info.name == "University Notice Board"

    async def test_get_board_by_id_not_found(self, board_manager: BoardManager):
        """Test retrieving a non-existent board."""
        board_info = await board_manager.get_board_by_id("nonexistent")
        assert board_info is None

    async def test_post_message(
        self, board_manager: BoardManager, student_board: BulletinBoard, sample_character: Character
    ):
        """Test posting a new message."""
        message = await board_manager.post_message(
            board_id="university_main",
            author_id=sample_character.id,
            subject="Test Subject",
            body="This is a test message body.",
        )
        assert message is not None
        assert message.subject == "Test Subject"
        assert message.body == "This is a test message body."
        assert message.author_name == "TestScholar"
        assert message.board_sequence == 1

    async def test_post_message_increments_sequence(
        self, board_manager: BoardManager, student_board: BulletinBoard, sample_character: Character
    ):
        """Test that posting messages increments sequence correctly."""
        msg1 = await board_manager.post_message(
            board_id="university_main",
            author_id=sample_character.id,
            subject="First Post",
            body="First body.",
        )
        msg2 = await board_manager.post_message(
            board_id="university_main",
            author_id=sample_character.id,
            subject="Second Post",
            body="Second body.",
        )
        assert msg1.board_sequence == 1
        assert msg2.board_sequence == 2

    async def test_post_anonymous_message(
        self, board_manager: BoardManager, public_board: BulletinBoard, sample_character: Character
    ):
        """Test posting an anonymous message."""
        message = await board_manager.post_message(
            board_id="imre_marketplace",
            author_id=sample_character.id,
            subject="Anonymous Post",
            body="Anonymous content.",
            is_anonymous=True,
        )
        assert message is not None
        assert message.is_anonymous is True

    async def test_post_reply(
        self, board_manager: BoardManager, student_board: BulletinBoard, sample_character: Character
    ):
        """Test posting a reply to an existing message."""
        parent = await board_manager.post_message(
            board_id="university_main",
            author_id=sample_character.id,
            subject="Original",
            body="Original content.",
        )
        reply = await board_manager.post_message(
            board_id="university_main",
            author_id=sample_character.id,
            subject="Re: Original",
            body="Reply content.",
            reply_to=parent.board_sequence,
        )
        assert reply is not None
        assert reply.reply_to_sequence == 1

    async def test_get_messages(
        self, board_manager: BoardManager, student_board: BulletinBoard, sample_character: Character
    ):
        """Test retrieving messages from a board."""
        # Post some messages
        await board_manager.post_message(
            board_id="university_main",
            author_id=sample_character.id,
            subject="Message 1",
            body="Body 1.",
        )
        await board_manager.post_message(
            board_id="university_main",
            author_id=sample_character.id,
            subject="Message 2",
            body="Body 2.",
        )

        messages = await board_manager.get_messages("university_main", sample_character.id)
        assert len(messages) == 2
        # Messages should be ordered by sequence (oldest first for reading)
        assert messages[0].subject == "Message 1"
        assert messages[1].subject == "Message 2"

    async def test_get_message_by_sequence(
        self, board_manager: BoardManager, student_board: BulletinBoard, sample_character: Character
    ):
        """Test retrieving a specific message by sequence number."""
        await board_manager.post_message(
            board_id="university_main",
            author_id=sample_character.id,
            subject="Target Message",
            body="Target body.",
        )

        message = await board_manager.get_message_by_sequence("university_main", 1)
        assert message is not None
        assert message.subject == "Target Message"

    async def test_delete_message_by_author(
        self,
        board_manager: BoardManager,
        student_board: BulletinBoard,
        sample_character: Character,
        db_session: AsyncSession,
    ):
        """Test that message author can delete their own message."""
        msg = await board_manager.post_message(
            board_id="university_main",
            author_id=sample_character.id,
            subject="To Delete",
            body="Delete me.",
        )

        deleted = await board_manager.delete_message(msg.id, sample_character.id)
        assert deleted is True

        # Verify message is gone
        messages = await board_manager.get_messages("university_main", sample_character.id)
        assert len(messages) == 0

    async def test_delete_message_by_non_author_denied(
        self,
        board_manager: BoardManager,
        student_board: BulletinBoard,
        sample_character: Character,
        advanced_character: Character,
        db_session: AsyncSession,
    ):
        """Test that non-author cannot delete message (unless moderator)."""
        msg = await board_manager.post_message(
            board_id="university_main",
            author_id=sample_character.id,
            subject="Protected",
            body="Cannot delete.",
        )

        # advanced_character is not the author
        deleted = await board_manager.delete_message(msg.id, advanced_character.id)
        assert deleted is False


class TestBoardManagerReadTracking:
    """Tests for message read tracking."""

    async def test_mark_as_read(
        self, board_manager: BoardManager, student_board: BulletinBoard, sample_character: Character
    ):
        """Test marking a message as read."""
        msg = await board_manager.post_message(
            board_id="university_main",
            author_id=sample_character.id,
            subject="Unread",
            body="Mark me read.",
        )

        await board_manager.mark_as_read(msg.id, sample_character.id)

        # Verify it's marked as read
        messages = await board_manager.get_messages("university_main", sample_character.id)
        assert len(messages) == 1
        assert messages[0].is_read is True

    async def test_get_unread_count(
        self,
        board_manager: BoardManager,
        student_board: BulletinBoard,
        sample_character: Character,
        advanced_character: Character,
        db_session: AsyncSession,
    ):
        """Test counting unread messages."""
        # Post messages as different character
        await board_manager.post_message(
            board_id="university_main",
            author_id=advanced_character.id,
            subject="Unread 1",
            body="Body 1.",
        )
        await board_manager.post_message(
            board_id="university_main",
            author_id=advanced_character.id,
            subject="Unread 2",
            body="Body 2.",
        )

        unread = await board_manager.get_unread_count("university_main", sample_character.id)
        assert unread == 2

    async def test_unread_count_decreases_after_read(
        self,
        board_manager: BoardManager,
        student_board: BulletinBoard,
        sample_character: Character,
        advanced_character: Character,
    ):
        """Test that unread count decreases after reading."""
        msg = await board_manager.post_message(
            board_id="university_main",
            author_id=advanced_character.id,
            subject="To Read",
            body="Read me.",
        )

        await board_manager.mark_as_read(msg.id, sample_character.id)

        unread = await board_manager.get_unread_count("university_main", sample_character.id)
        assert unread == 0


class TestBoardManagerPruning:
    """Tests for message pruning."""

    async def test_prune_old_messages(
        self, board_manager: BoardManager, db_session: AsyncSession, sample_character: Character
    ):
        """Test pruning old messages when max is exceeded."""
        # Create a board with max 3 messages
        board = BulletinBoard(
            id="small_board",
            name="Small Board",
            description="A small board for testing pruning.",
            room_id="test_room",
            read_level=BoardAccessLevel.PUBLIC,
            post_level=BoardAccessLevel.PUBLIC,
            max_messages=3,
        )
        db_session.add(board)
        await db_session.commit()

        # Post 5 messages
        for i in range(5):
            await board_manager.post_message(
                board_id="small_board",
                author_id=sample_character.id,
                subject=f"Message {i + 1}",
                body=f"Body {i + 1}.",
            )

        # Prune should remove 2 messages
        pruned = await board_manager.prune_old_messages("small_board")
        assert pruned == 2

        # Should only have 3 messages left
        messages = await board_manager.get_messages("small_board", sample_character.id)
        assert len(messages) == 3
        # Should keep the newest (3, 4, 5)
        subjects = [m.subject for m in messages]
        assert "Message 3" in subjects
        assert "Message 4" in subjects
        assert "Message 5" in subjects

    async def test_prune_preserves_pinned_messages(
        self,
        board_manager: BoardManager,
        db_session: AsyncSession,
        sample_character: Character,
        master_character: Character,
    ):
        """Test that pruning preserves pinned messages."""
        board = BulletinBoard(
            id="pinned_board",
            name="Pinned Board",
            description="Board with pinned messages.",
            room_id="test_room",
            read_level=BoardAccessLevel.PUBLIC,
            post_level=BoardAccessLevel.PUBLIC,
            max_messages=3,
        )
        db_session.add(board)
        await db_session.commit()

        # Post a pinned message first
        pinned = await board_manager.post_message(
            board_id="pinned_board",
            author_id=sample_character.id,
            subject="Pinned Important",
            body="This is pinned.",
        )
        await board_manager.pin_message(pinned.id, master_character.id)

        # Post 4 more messages
        for i in range(4):
            await board_manager.post_message(
                board_id="pinned_board",
                author_id=sample_character.id,
                subject=f"Normal {i + 1}",
                body=f"Normal body {i + 1}.",
            )

        # Prune
        await board_manager.prune_old_messages("pinned_board")

        # Verify pinned message is still there
        messages = await board_manager.get_messages("pinned_board", sample_character.id)
        subjects = [m.subject for m in messages]
        assert "Pinned Important" in subjects


class TestBoardManagerPinning:
    """Tests for message pinning."""

    async def test_pin_message_by_master(
        self,
        board_manager: BoardManager,
        student_board: BulletinBoard,
        sample_character: Character,
        master_character: Character,
    ):
        """Test that El'the can pin messages."""
        msg = await board_manager.post_message(
            board_id="university_main",
            author_id=sample_character.id,
            subject="To Pin",
            body="Pin me.",
        )

        pinned = await board_manager.pin_message(msg.id, master_character.id)
        assert pinned is True

        # Verify it's pinned
        message = await board_manager.get_message_by_sequence("university_main", 1)
        assert message is not None
        assert message.is_pinned is True

    async def test_pin_message_by_non_master_denied(
        self, board_manager: BoardManager, student_board: BulletinBoard, sample_character: Character
    ):
        """Test that non-masters cannot pin messages."""
        msg = await board_manager.post_message(
            board_id="university_main",
            author_id=sample_character.id,
            subject="Cannot Pin",
            body="No pin for you.",
        )

        pinned = await board_manager.pin_message(msg.id, sample_character.id)
        assert pinned is False


class TestMessageFormatter:
    """Tests for MessageFormatter."""

    def test_format_board_list(self):
        """Test formatting a list of boards."""
        boards = [
            BoardInfo(
                id="board1",
                name="Board One",
                description="First board.",
                room_id="room1",
                read_level=BoardAccessLevel.PUBLIC,
                post_level=BoardAccessLevel.PUBLIC,
                max_messages=50,
                allow_anonymous=False,
                is_active=True,
                message_count=10,
                unread_count=3,
            ),
            BoardInfo(
                id="board2",
                name="Board Two",
                description="Second board.",
                room_id="room1",
                read_level=BoardAccessLevel.STUDENT,
                post_level=BoardAccessLevel.STUDENT,
                max_messages=50,
                allow_anonymous=False,
                is_active=True,
                message_count=5,
                unread_count=0,
            ),
        ]

        character = MagicMock()
        character.arcanum_rank = "e_lir"

        output = MessageFormatter.format_board_list(boards, character)
        assert "Board One" in output
        assert "Board Two" in output
        assert "[NEW]" in output or "3" in output  # Should indicate unread

    def test_format_message_list(self):
        """Test formatting a list of messages."""
        now = datetime.now(UTC)
        messages = [
            MessageInfo(
                id=uuid.uuid4(),
                board_id="test",
                author_name="Author1",
                subject="Subject One",
                body="Body one.",
                board_sequence=1,
                is_pinned=True,
                is_anonymous=False,
                is_read=True,
                created_at=now,
                reply_to=None,
                reply_to_sequence=None,
            ),
            MessageInfo(
                id=uuid.uuid4(),
                board_id="test",
                author_name="Author2",
                subject="Subject Two",
                body="Body two.",
                board_sequence=2,
                is_pinned=False,
                is_anonymous=False,
                is_read=False,
                created_at=now,
                reply_to=None,
                reply_to_sequence=None,
            ),
        ]

        character = MagicMock()

        output = MessageFormatter.format_message_list(messages, character)
        assert "Subject One" in output
        assert "Subject Two" in output
        assert "[NEW]" in output  # Second message is unread
        assert "Author1" in output

    def test_format_message(self):
        """Test formatting a single message."""
        now = datetime.now(UTC)
        message = MessageInfo(
            id=uuid.uuid4(),
            board_id="test",
            author_name="Simmon",
            subject="Equipment for sale",
            body="I have some sympathy lamps available.",
            board_sequence=5,
            is_pinned=False,
            is_anonymous=False,
            is_read=True,
            created_at=now,
            reply_to=None,
            reply_to_sequence=None,
        )

        character = MagicMock()

        output = MessageFormatter.format_message(message, character, total_messages=12)
        # Check for ANSI-style borders
        assert "Message #5" in output
        assert "Simmon" in output
        assert "Equipment for sale" in output
        assert "I have some sympathy lamps" in output

    def test_format_message_anonymous(self):
        """Test formatting an anonymous message."""
        now = datetime.now(UTC)
        message = MessageInfo(
            id=uuid.uuid4(),
            board_id="test",
            author_name="SecretAuthor",
            subject="Anonymous Post",
            body="Secret content.",
            board_sequence=1,
            is_pinned=False,
            is_anonymous=True,
            is_read=True,
            created_at=now,
            reply_to=None,
            reply_to_sequence=None,
        )

        character = MagicMock()

        output = MessageFormatter.format_message(message, character, total_messages=1)
        # Should show "Anonymous" instead of the actual author
        assert "Anonymous" in output
        assert "SecretAuthor" not in output

    def test_format_board_header(self):
        """Test formatting a board header."""
        board = BoardInfo(
            id="test_board",
            name="Test Board",
            description="A test board.",
            room_id="test_room",
            read_level=BoardAccessLevel.PUBLIC,
            post_level=BoardAccessLevel.STUDENT,
            max_messages=50,
            allow_anonymous=False,
            is_active=True,
            message_count=10,
            unread_count=3,
        )

        output = MessageFormatter.format_board_header(board, 3)
        assert "Test Board" in output
        assert "3" in output  # Unread count
