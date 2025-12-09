"""Shared fixtures for game tests."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from waystone.database.models import Base, Character, CharacterBackground, User


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


@pytest.fixture
async def test_user(db_session: AsyncSession):
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
async def test_character(db_session: AsyncSession, test_user):
    """Create a test character."""
    character = Character(
        user_id=test_user.id,
        name="TestChar",
        background=CharacterBackground.SCHOLAR,
        current_room_id="university_main_gates",
        strength=10,
        dexterity=10,
        constitution=10,
        intelligence=10,
        wisdom=10,
        charisma=10,
    )
    db_session.add(character)
    await db_session.commit()
    await db_session.refresh(character)
    return character
