"""Shared fixtures for all tests."""

import os

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from waystone.database.models import Base, Character, CharacterBackground, User


# CRITICAL: Set test database URL BEFORE any waystone imports can cache it
# This prevents tests from using/modifying the production database
@pytest.fixture(scope="session", autouse=True)
def use_test_database(tmp_path_factory):
    """Force all tests to use a temporary database instead of production.

    This fixture runs automatically at the start of the test session and
    ensures that get_session() calls use a test database, not production.
    The test database is deleted after all tests complete.
    """
    # Create a temp directory for the test database
    test_db_dir = tmp_path_factory.mktemp("waystone_test")
    test_db_path = test_db_dir / "test_waystone.db"

    # Set environment variable before settings are loaded
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{test_db_path}"

    # Reset the cached engine/session factory if they exist
    import waystone.database.engine as engine_module
    engine_module._engine = None
    engine_module._async_session_factory = None

    # Also clear any cached settings
    from waystone.config import get_settings
    get_settings.cache_clear()

    yield

    # Cleanup after all tests
    if engine_module._engine is not None:
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(engine_module._engine.dispose())
            else:
                loop.run_until_complete(engine_module._engine.dispose())
        except RuntimeError:
            pass

    engine_module._engine = None
    engine_module._async_session_factory = None

    # The temp directory is automatically cleaned up by pytest


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
async def sample_user(db_session: AsyncSession):
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
async def test_user(db_session: AsyncSession):
    """Create a test user (alias for sample_user)."""
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
