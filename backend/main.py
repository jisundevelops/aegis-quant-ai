"""
backend.main — FastAPI application entry point.

Boots the API, configures logging, wires routers, and exposes the ASGI
`app` object consumed by uvicorn.

Run:
    uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import admin, analyze, backtest, health, market_data, signals
from backend.core.exceptions import register_exception_handlers
from backend.core.logging import configure_logging
from config import settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application startup and shutdown lifecycle."""
    configure_logging()
    # Phase 2: warm the DB engine + Redis client (lazy singletons).
    try:
        from database.connection import close_all, get_async_engine, get_redis

        get_async_engine()
        get_redis()
        app.state.db_ready = True
        app.state.redis_ready = True
    except Exception as exc:  # noqa: BLE001 — let app boot even if DB is down
        app.state.db_ready = False
        app.state.redis_ready = False
        app.state.db_error = str(exc)

    # Phase 3: start the data collection scheduler (toggleable).
    app.state.scheduler = None
    if settings.scheduler_enabled:
        try:
            from data.scheduler import start_scheduler, stop_scheduler
            app.state.scheduler = start_scheduler()
        except Exception as exc:  # noqa: BLE001
            app.state.scheduler_error = str(exc)

    yield

    # Phase 3: shut down the scheduler first (closes connectors).
    if app.state.scheduler is not None:
        try:
            from data.scheduler import stop_scheduler
            await stop_scheduler()
        except Exception:  # noqa: BLE001
            pass

    # Phase 2: release DB + Redis resources.
    try:
        await close_all()
    except Exception:  # noqa: BLE001
        pass


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
# if needed (the Next.js rewrite proxy is the primary path, but this is
# a safety net for direct API access from browsers, mobile apps, etc.)
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
