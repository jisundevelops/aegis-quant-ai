"""
database.connection — Async PostgreSQL + Redis connection handlers.

Exposes:
  - get_async_engine()   Singleton async SQLAlchemy engine (asyncpg)
  - get_async_session()  FastAPI dependency yielding an AsyncSession
  - get_redis()          Singleton async Redis client
  - init_db()            Create all tables (dev / test convenience)
  - close_all()          Dispose engine + close Redis (for app shutdown)

All URLs are sourced from `config.settings` — never hardcoded.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.core.exceptions import ConfigurationError
from config import settings

try:
    from redis.asyncio import Redis, from_url as redis_from_url
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "redis package is required. Install with: pip install redis"
    ) from exc


# --------------------------------------------------------------------
# Module-level singletons (lazily initialized)
# --------------------------------------------------------------------
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_redis: Redis | None = None


# --------------------------------------------------------------------
# PostgreSQL
# --------------------------------------------------------------------
def get_async_engine() -> AsyncEngine:
    """Return the singleton async engine, creating it on first call.

    Engine configuration:
      - pool_pre_ping=True: tests each connection before use (catches drops)
      - pool_size=10, max_overflow=20 (from settings)
      - pool_recycle=1800: recycle connections after 30 minutes (prevents
        stale connections from Supabase/Render network changes)
    """
    global _engine
    if _engine is None:
        dsn = settings.postgres_dsn
        if not dsn:
            raise ConfigurationError(
                "No DATABASE_URL or POSTGRES_* fields configured. "
                "Set DATABASE_URL in .env."
            )
        if dsn.startswith("file:"):
            raise ConfigurationError(
                f"DATABASE_URL points to a local file ({dsn}). "
                "It must be a PostgreSQL URL (postgresql+asyncpg://...). "
                "Set DATABASE_URL in your Render dashboard to your Supabase URL."
            )
        _engine = create_async_engine(
            dsn,
            echo=False,
            pool_pre_ping=True,       # Test each connection before use
            pool_size=settings.postgres_pool_size,
            max_overflow=settings.postgres_max_overflow,
            pool_recycle=1800,        # Recycle connections every 30 minutes
            pool_timeout=10,          # Wait up to 10s for a connection
        )
    return _engine


def get_async_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return a cached async session factory bound to the singleton engine."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_async_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def get_async_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yield an AsyncSession, auto-close on exit."""
    factory = get_async_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def async_session_ctx() -> AsyncIterator[AsyncSession]:
    """Standalone async context manager for non-FastAPI callers (scripts, tests)."""
    factory = get_async_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


# --------------------------------------------------------------------
# Redis
# --------------------------------------------------------------------
def get_redis() -> Redis:
    """Return the singleton async Redis client, creating it on first call."""
    global _redis
    if _redis is None:
        url = settings.effective_redis_url
        if not url:
            raise ConfigurationError(
                "No REDIS_URL or REDIS_* fields configured. Set REDIS_URL in .env."
            )
        _redis = redis_from_url(
            url,
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5,
            health_check_interval=30,
        )
    return _redis


# --------------------------------------------------------------------
# Lifecycle helpers
# --------------------------------------------------------------------
async def init_db() -> None:
    """Create all tables defined on Base.metadata.

    Intended for development and tests. Production uses Alembic migrations.
    """
    from database.models import Base  # local import to avoid cycle

    engine = get_async_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_all() -> None:
    """Dispose the async engine and close the Redis client.

    Call on application shutdown.
    """
    global _engine, _session_factory, _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


__all__ = [
    "get_async_engine",
    "get_async_session",
    "get_async_session_factory",
    "async_session_ctx",
    "get_redis",
    "init_db",
    "close_all",
]
