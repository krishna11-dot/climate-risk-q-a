"""Async PostgreSQL connection management via SQLAlchemy's asyncpg driver.

Provides a process-wide connection pool (min 2, max 10 connections) and
an async session factory used by every module that touches the database.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import config

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Returns the process-wide async SQLAlchemy engine, creating it on
    first use with the configured connection pool bounds.

    Returns:
        The shared AsyncEngine instance.
    """
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            config.DATABASE_URL,
            pool_size=config.DB_POOL_MIN_SIZE,
            max_overflow=config.DB_POOL_MAX_SIZE - config.DB_POOL_MIN_SIZE,
            pool_pre_ping=True,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Returns the process-wide async session factory.

    Returns:
        The shared async_sessionmaker instance.
    """
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(), expire_on_commit=False
        )
    return _session_factory


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Async context manager yielding a database session.

    Yields:
        An AsyncSession bound to the shared connection pool.
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        yield session


async def dispose_engine() -> None:
    """Disposes the engine and its connection pool. Call on app shutdown."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
