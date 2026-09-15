"""Async SQLAlchemy database primitives for the control plane."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from bff_control.core.settings import DatabaseSettings


class Database:
    """Own the control-plane async engine and session factory.

    The object is explicit rather than module-global so tests and future process
    entrypoints can own lifecycle cleanly.
    """

    def __init__(self, settings: DatabaseSettings) -> None:
        self._engine: AsyncEngine = create_async_engine(
            settings.database_url.get_secret_value(),
            pool_pre_ping=True,
            pool_recycle=1800,
        )
        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Yield a session without implicit commit.

        Transaction ownership belongs to the calling service. On exceptions we
        roll back any open transaction before releasing the session.
        """

        async with self._session_factory() as session:
            try:
                yield session
            except BaseException:
                await session.rollback()
                raise

    async def dispose(self) -> None:
        """Release all pooled database connections."""

        await self._engine.dispose()
