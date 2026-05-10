"""
Async database engine setup.
Supports both SQLite (dev) and PostgreSQL (production via Neon).
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from src.config import get_settings

logger = logging.getLogger(__name__)

_engine = None
_async_session_factory = None


def get_engine():
    """Create or return the async database engine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        db_url = settings.database_url

        # Connection pool settings differ for SQLite vs PostgreSQL
        if "sqlite" in db_url:
            _engine = create_async_engine(
                db_url,
                echo=(settings.log_level == "DEBUG"),
                connect_args={"check_same_thread": False},
            )
        else:
            _engine = create_async_engine(
                db_url,
                echo=(settings.log_level == "DEBUG"),
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,  # Handle Neon cold starts
            )
        logger.info(f"Database engine created: {db_url.split('@')[-1] if '@' in db_url else db_url}")
    return _engine


def get_session_factory():
    """Get the async session factory."""
    global _async_session_factory
    if _async_session_factory is None:
        engine = get_engine()
        _async_session_factory = sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _async_session_factory


async def get_session() -> AsyncSession:
    """Create a new async database session."""
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def init_db() -> None:
    """Initialize the database — create all tables."""
    # Import models so SQLModel registers them
    import src.db.models  # noqa: F401

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    logger.info("Database tables initialized successfully")


async def close_db() -> None:
    """Close the database engine and clean up connections."""
    global _engine, _async_session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _async_session_factory = None
        logger.info("Database connections closed")
