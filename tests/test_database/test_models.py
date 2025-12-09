"""Tests for SQLAlchemy database models."""

import uuid
from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from waystone.database.models import (
    Base,
    Character,
    CharacterBackground,
    Room,
    User,
)


@pytest.fixture
async def db_session():
    """Create a test database session with in-memory SQLite."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        yield session
        await session.rollback()

    await engine.dispose()


class TestUserModel:
    """Tests for User model."""

    async def test_user_creation(self, db_session: AsyncSession):
        """Test creating a user with hashed password."""
        password = "secure_password_123"
        password_hash = User.hash_password(password)

        user = User(
            username="testuser",
            email="test@example.com",
            password_hash=password_hash,
        )

        db_session.add(user)
        await db_session.commit()

        assert user.id is not None
        assert isinstance(user.id, uuid.UUID)
        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.is_admin is False
        assert user.created_at is not None
        assert user.updated_at is not None
        assert isinstance(user.created_at, datetime)

    async def test_password_hashing(self):
        """Test password hashing creates different hashes."""
        password = "my_password"
        hash1 = User.hash_password(password)
        hash2 = User.hash_password(password)

        # Hashes should be different due to salt
        assert hash1 != hash2
        assert len(hash1) > 0
        assert len(hash2) > 0

    async def test_password_verification(self, db_session: AsyncSession):
        """Test password verification works correctly."""
        password = "correct_password"
        user = User(
            username="authuser",
            email="auth@example.com",
            password_hash=User.hash_password(password),
        )

        # Correct password should verify
        assert user.verify_password(password) is True

        # Wrong password should not verify
        assert user.verify_password("wrong_password") is False
        assert user.verify_password("") is False

    async def test_unique_username_constraint(self, db_session: AsyncSession):
        """Test that usernames must be unique."""
        user1 = User(
            username="duplicate",
            email="user1@example.com",
            password_hash=User.hash_password("password1"),
        )
        db_session.add(user1)
        await db_session.commit()

        user2 = User(
            username="duplicate",
            email="user2@example.com",
            password_hash=User.hash_password("password2"),
        )
        db_session.add(user2)

        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_unique_email_constraint(self, db_session: AsyncSession):
        """Test that emails must be unique."""
        user1 = User(
            username="user1",
            email="duplicate@example.com",
            password_hash=User.hash_password("password1"),
        )
        db_session.add(user1)
        await db_session.commit()

        user2 = User(
            username="user2",
            email="duplicate@example.com",
            password_hash=User.hash_password("password2"),
        )
        db_session.add(user2)

        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_user_repr(self, db_session: AsyncSession):
        """Test user string representation."""
        user = User(
            username="repruser",
            email="repr@example.com",
            password_hash=User.hash_password("password"),
        )
        db_session.add(user)
        await db_session.commit()

        repr_str = repr(user)
        assert "User" in repr_str
        assert "repruser" in repr_str
        assert "repr@example.com" in repr_str


class TestCharacterModel:
    """Tests for Character model."""

    async def test_character_creation(self, db_session: AsyncSession):
        """Test creating a character with valid background."""
        # Create user first
        user = User(
            username="player",
            email="player@example.com",
            password_hash=User.hash_password("password"),
        )
        db_session.add(user)
        await db_session.commit()

        # Create character
        character = Character(
            user_id=user.id,
            name="Kvothe",
            background=CharacterBackground.SCHOLAR,
            current_room_id="university_main_gates",
        )
        db_session.add(character)
        await db_session.commit()

        assert character.id is not None
        assert isinstance(character.id, uuid.UUID)
        assert character.name == "Kvothe"
        assert character.background == CharacterBackground.SCHOLAR
        assert character.user_id == user.id
        assert character.current_room_id == "university_main_gates"

        # Check default attributes
        assert character.strength == 10
        assert character.dexterity == 10
        assert character.constitution == 10
        assert character.intelligence == 10
        assert character.wisdom == 10
        assert character.charisma == 10
        assert character.level == 1
        assert character.experience == 0

    async def test_character_backgrounds(self, db_session: AsyncSession):
        """Test all character backgrounds are valid."""
        user = User(
            username="bgplayer",
            email="bg@example.com",
            password_hash=User.hash_password("password"),
        )
        db_session.add(user)
        await db_session.commit()

        backgrounds = [
            CharacterBackground.SCHOLAR,
            CharacterBackground.MERCHANT,
            CharacterBackground.PERFORMER,
            CharacterBackground.WAYFARER,
            CharacterBackground.NOBLE,
            CharacterBackground.COMMONER,
        ]

        for idx, background in enumerate(backgrounds):
            character = Character(
                user_id=user.id,
                name=f"Character{idx}",
                background=background,
                current_room_id="starting_room",
            )
            db_session.add(character)

        await db_session.commit()

        # Verify all characters were created
        result = await db_session.execute(select(Character))
        characters = result.scalars().all()
        assert len(characters) == len(backgrounds)

    async def test_character_custom_attributes(self, db_session: AsyncSession):
        """Test creating character with custom attributes."""
        user = User(
            username="attrplayer",
            email="attr@example.com",
            password_hash=User.hash_password("password"),
        )
        db_session.add(user)
        await db_session.commit()

        character = Character(
            user_id=user.id,
            name="CustomChar",
            background=CharacterBackground.NOBLE,
            current_room_id="noble_quarter",
            strength=15,
            dexterity=12,
            constitution=14,
            intelligence=16,
            wisdom=13,
            charisma=18,
            level=5,
            experience=10000,
        )
        db_session.add(character)
        await db_session.commit()

        assert character.strength == 15
        assert character.dexterity == 12
        assert character.constitution == 14
        assert character.intelligence == 16
        assert character.wisdom == 13
        assert character.charisma == 18
        assert character.level == 5
        assert character.experience == 10000

    async def test_unique_character_name(self, db_session: AsyncSession):
        """Test that character names must be unique."""
        user = User(
            username="nameplayer",
            email="name@example.com",
            password_hash=User.hash_password("password"),
        )
        db_session.add(user)
        await db_session.commit()

        char1 = Character(
            user_id=user.id,
            name="Duplicate",
            background=CharacterBackground.SCHOLAR,
            current_room_id="room1",
        )
        db_session.add(char1)
        await db_session.commit()

        char2 = Character(
            user_id=user.id,
            name="Duplicate",
            background=CharacterBackground.MERCHANT,
            current_room_id="room2",
        )
        db_session.add(char2)

        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_character_user_relationship(self, db_session: AsyncSession):
        """Test relationship between character and user."""
        user = User(
            username="relplayer",
            email="rel@example.com",
            password_hash=User.hash_password("password"),
        )
        db_session.add(user)
        await db_session.commit()

        character = Character(
            user_id=user.id,
            name="RelChar",
            background=CharacterBackground.PERFORMER,
            current_room_id="stage",
        )
        db_session.add(character)
        await db_session.commit()

        # Refresh to load relationships
        await db_session.refresh(user, ["characters"])
        await db_session.refresh(character, ["user"])

        # Test relationship
        assert character.user.username == "relplayer"
        assert character in user.characters

    async def test_character_cascade_delete(self, db_session: AsyncSession):
        """Test that characters are deleted when user is deleted."""
        user = User(
            username="deleteplayer",
            email="delete@example.com",
            password_hash=User.hash_password("password"),
        )
        db_session.add(user)
        await db_session.commit()

        character = Character(
            user_id=user.id,
            name="DeleteChar",
            background=CharacterBackground.WAYFARER,
            current_room_id="road",
        )
        db_session.add(character)
        await db_session.commit()

        user_id = user.id

        # Delete user
        await db_session.delete(user)
        await db_session.commit()

        # Character should be deleted too
        result = await db_session.execute(select(Character).where(Character.user_id == user_id))
        characters = result.scalars().all()
        assert len(characters) == 0

    async def test_character_repr(self, db_session: AsyncSession):
        """Test character string representation."""
        user = User(
            username="reprplayer",
            email="reprchar@example.com",
            password_hash=User.hash_password("password"),
        )
        db_session.add(user)
        await db_session.commit()

        character = Character(
            user_id=user.id,
            name="ReprChar",
            background=CharacterBackground.COMMONER,
            current_room_id="village",
            level=3,
        )
        db_session.add(character)
        await db_session.commit()

        repr_str = repr(character)
        assert "Character" in repr_str
        assert "ReprChar" in repr_str
        assert "Commoner" in repr_str
        assert "level=3" in repr_str


class TestRoomModel:
    """Tests for Room model."""

    async def test_room_creation(self, db_session: AsyncSession):
        """Test creating a room with exits and properties."""
        room = Room(
            id="university_archives",
            name="The Archives",
            description="A vast library filled with countless books and scrolls.",
            area="university",
            exits={"north": "university_courtyard", "south": "archives_basement"},
            properties={"indoor": True, "lit": True, "safe_zone": True, "quiet": True},
        )
        db_session.add(room)
        await db_session.commit()

        assert room.id == "university_archives"
        assert room.name == "The Archives"
        assert room.area == "university"
        assert "north" in room.exits
        assert room.exits["north"] == "university_courtyard"
        assert room.properties["indoor"] is True
        assert room.properties["safe_zone"] is True

    async def test_room_empty_exits(self, db_session: AsyncSession):
        """Test creating a room with no exits."""
        room = Room(
            id="dead_end",
            name="Dead End",
            description="A corridor that goes nowhere.",
            area="dungeon",
            exits={},
            properties={},
        )
        db_session.add(room)
        await db_session.commit()

        assert len(room.exits) == 0
        assert len(room.properties) == 0

    async def test_room_complex_exits(self, db_session: AsyncSession):
        """Test room with multiple directional exits."""
        room = Room(
            id="crossroads",
            name="Crossroads",
            description="Four paths meet here.",
            area="wilderness",
            exits={
                "north": "northern_road",
                "south": "southern_road",
                "east": "eastern_road",
                "west": "western_road",
                "up": "tower_entrance",
                "down": "cellar",
            },
            properties={"outdoor": True, "lit": False},
        )
        db_session.add(room)
        await db_session.commit()

        assert len(room.exits) == 6
        assert room.exits["north"] == "northern_road"
        assert room.exits["up"] == "tower_entrance"
        assert room.properties["outdoor"] is True
        assert room.properties["lit"] is False

    async def test_room_unique_id(self, db_session: AsyncSession):
        """Test that room IDs must be unique."""
        room1 = Room(
            id="duplicate_room",
            name="First Room",
            description="First room.",
            area="area1",
        )
        db_session.add(room1)
        await db_session.commit()

        room2 = Room(
            id="duplicate_room",
            name="Second Room",
            description="Second room.",
            area="area2",
        )
        db_session.add(room2)

        with pytest.raises(IntegrityError):
            await db_session.commit()

    async def test_room_repr(self, db_session: AsyncSession):
        """Test room string representation."""
        room = Room(
            id="test_room",
            name="Test Room",
            description="A test room.",
            area="test_area",
        )
        db_session.add(room)
        await db_session.commit()

        repr_str = repr(room)
        assert "Room" in repr_str
        assert "test_room" in repr_str
        assert "Test Room" in repr_str
        assert "test_area" in repr_str
