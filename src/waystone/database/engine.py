"""Async SQLAlchemy engine and session management for Waystone MUD."""

from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from waystone.config import get_settings

from .models.base import Base

# Global engine and session factory
_engine: AsyncEngine | None = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None

# Sync engine for legacy code paths
_sync_engine: Engine | None = None
_sync_session_factory: sessionmaker[Session] | None = None


def get_engine() -> AsyncEngine:
    """
    Get or create the async SQLAlchemy engine.

    Returns:
        The async database engine
    """
    global _engine

    if _engine is None:
        settings = get_settings()

        # Ensure data directory exists for SQLite
        if settings.database_url.startswith("sqlite"):
            db_path = settings.database_url.split("///")[-1]
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        _engine = create_async_engine(
            settings.database_url,
            echo=settings.debug,
            future=True,
        )

    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """
    Get or create the async session factory.

    Returns:
        The async session factory
    """
    global _async_session_factory

    if _async_session_factory is None:
        engine = get_engine()
        _async_session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    return _async_session_factory


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager for database sessions.

    Yields:
        An async database session

    Example:
        async with get_session() as session:
            user = await session.get(User, user_id)
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """
    Initialize the database by creating all tables.

    This should be called on application startup.
    """
    engine = get_engine()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """
    Close the database engine and cleanup resources.

    This should be called on application shutdown.
    """
    global _engine, _async_session_factory, _sync_engine, _sync_session_factory

    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _async_session_factory = None

    if _sync_engine is not None:
        _sync_engine.dispose()
        _sync_engine = None
        _sync_session_factory = None


def get_sync_engine() -> Engine:
    """
    Get or create the sync SQLAlchemy engine.

    Used for legacy synchronous code paths.
    """
    global _sync_engine

    if _sync_engine is None:
        settings = get_settings()

        # Convert async URL to sync URL
        db_url = settings.database_url
        if "aiosqlite" in db_url:
            db_url = db_url.replace("sqlite+aiosqlite", "sqlite")
        elif "asyncpg" in db_url:
            db_url = db_url.replace("postgresql+asyncpg", "postgresql+psycopg2")

        # Ensure data directory exists for SQLite
        if db_url.startswith("sqlite"):
            db_path = db_url.split("///")[-1]
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        _sync_engine = create_engine(
            db_url,
            echo=settings.debug,
            future=True,
        )

    return _sync_engine


def get_sync_session_factory() -> sessionmaker[Session]:
    """
    Get or create the sync session factory.
    """
    global _sync_session_factory

    if _sync_session_factory is None:
        engine = get_sync_engine()
        _sync_session_factory = sessionmaker(
            engine,
            class_=Session,
            expire_on_commit=False,
        )

    return _sync_session_factory


@contextmanager
def get_sync_session() -> Generator[Session, None, None]:
    """
    Sync context manager for database sessions.

    Used for legacy synchronous code paths.

    Yields:
        A sync database session

    Example:
        with get_sync_session() as session:
            user = session.get(User, user_id)
    """
    factory = get_sync_session_factory()
    with factory() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
