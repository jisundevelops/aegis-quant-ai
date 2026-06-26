"""
backend.main — FastAPI application entry point.

Boots the API, configures logging, wires routers, and exposes the ASGI
`app` object consumed by uvicorn.

Run:
    uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

Render deployment note:
    The lifespan function MUST complete quickly so uvicorn can bind to
    $PORT before Render's port scanner times out (~60s). All slow
    operations (DB warmup, scheduler start, initial data fetch) are
    deferred to a background task that runs AFTER the app is listening.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from backend.api.routes import admin, analyze, backtest, health, market_data, signals
from backend.core.exceptions import register_exception_handlers
from backend.core.logging import configure_logging
from config import settings


async def _deferred_startup() -> None:
    """Background task that runs AFTER the app is listening on $PORT.

    This does the slow work:
      1. Warm the DB engine + Redis client (lazy singletons)
      2. Actually TEST the DB connection with SELECT 1
      3. Start the APScheduler (which triggers an immediate data fetch)

    Any errors are logged but do NOT crash the app — the API stays up
    even if the DB is unreachable (endpoints will return 503/404 with
    helpful error messages via /api/admin/diagnose).
    """
    # Small delay to ensure uvicorn has fully bound the port
    await asyncio.sleep(1.0)

    # 1. Warm DB + Redis (creates engine/client — does NOT test connection)
    try:
        from database.connection import get_async_engine, get_redis
        get_async_engine()
        get_redis()
        logger.info("✅ DB engine + Redis client created (connection not yet tested)")
    except Exception as exc:  # noqa: BLE001
        logger.error("❌ DB/Redis engine creation failed: {} — call /api/admin/diagnose", exc)
        return  # No point continuing if engine creation fails

    # 2. Actually TEST the DB connection with SELECT 1
    #    (engine creation is lazy — this is the first real network call)
    try:
        from sqlalchemy import text as sql_text
        from database.connection import async_session_ctx
        async with async_session_ctx() as session:
            await session.execute(sql_text("SELECT 1"))
        logger.info("✅ Database connection verified (SELECT 1 succeeded)")
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "❌ Database connection FAILED: {}\n"
            "  → The DB engine was created but cannot connect.\n"
            "  → Check GET /api/admin/diagnose for details.\n"
            "  → Common causes:\n"
            "    1. DATABASE_URL not set on Render (check Environment tab)\n"
            "    2. DATABASE_URL points to localhost (must be Supabase URL)\n"
            "    3. Supabase project is paused (free tier auto-pauses)\n"
            "    4. Password not URL-encoded (@ must be %40)",
            exc
        )
        return  # Don't start scheduler if DB is broken — it will just fail

    # 3. Start scheduler (triggers immediate data fetch)
    if settings.scheduler_enabled:
        try:
            from data.scheduler import start_scheduler
            start_scheduler()
            logger.info("✅ Scheduler started — initial data fetch in progress")
        except Exception as exc:  # noqa: BLE001
            logger.error("❌ Scheduler start failed: {}", exc)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application startup and shutdown lifecycle.

    CRITICAL: This function MUST complete quickly (under 5 seconds) so
    uvicorn can bind to $PORT before Render's port scanner times out.

    All slow operations (DB warmup, scheduler start) are deferred to
    a background task via asyncio.create_task().
    """
    configure_logging()
    logger.info("Starting Aegis Quant AI v{}...", settings.app_version)

    # Mark DB/Redis as not-yet-ready (will be set by _deferred_startup)
    app.state.db_ready = False
    app.state.redis_ready = False
    app.state.scheduler = None

    # Launch deferred startup in the background — does NOT block the
    # lifespan from completing, so uvicorn binds to $PORT immediately.
    startup_task = asyncio.create_task(_deferred_startup())

    yield

    # ── Shutdown ────────────────────────────────────────────────────
    startup_task.cancel()
    try:
        await startup_task
    except asyncio.CancelledError:
        pass

    # Shut down the scheduler (closes connectors)
    try:
        from data.scheduler import stop_scheduler
        await stop_scheduler()
    except Exception:  # noqa: BLE001
        pass

    # Release DB + Redis resources
    try:
        from database.connection import close_all
        await close_all()
    except Exception:  # noqa: BLE001
        pass
    logger.info("Aegis Quant AI shut down.")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Modular, institutional-grade AI trading research assistant.",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS middleware — allows the Vercel frontend to call the API directly
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to your Vercel domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register global exception handlers.
register_exception_handlers(app)

# Wire routers.
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(market_data.router, prefix="/api/market-data", tags=["market-data"])
app.include_router(signals.router, prefix="/api/signals", tags=["signals"])
app.include_router(analyze.router, prefix="/api", tags=["analyze"])
app.include_router(backtest.router, prefix="/api", tags=["backtest"])
app.include_router(admin.router, prefix="/api", tags=["admin"])


@app.get("/", tags=["root"])
async def root() -> dict[str, str]:
    """Root metadata endpoint."""
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "env": settings.app_env,
        "docs": "/docs",
    }
