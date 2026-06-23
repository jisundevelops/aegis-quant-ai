"""
backend.api.routes.health — Liveness and readiness probes.
"""
from __future__ import annotations

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from config import settings

router = APIRouter()


@router.get("/health", status_code=status.HTTP_200_OK)
async def health() -> dict[str, str]:
    """Liveness probe — process is up."""
    return {"status": "ok"}


@router.get("/health/ready", status_code=status.HTTP_200_OK)
async def readiness(request: Request) -> JSONResponse:
    """Readiness probe — verify DB + Redis connectivity.

    Reports each dependency's status separately. Returns 503 if any
    critical dependency is unreachable so orchestrators don't route
    traffic to a half-broken instance.
    """
    db_ok = False
    redis_ok = False
    db_error: str | None = None
    redis_error: str | None = None

    # ---------- PostgreSQL ----------
    try:
        from database.connection import async_session_ctx

        async with async_session_ctx() as session:
            await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:  # noqa: BLE001
        db_error = str(exc)[:200]

    # ---------- Redis ----------
    try:
        from database.connection import get_redis

        await get_redis().ping()
        redis_ok = True
    except Exception as exc:  # noqa: BLE001
        redis_error = str(exc)[:200]

    healthy = db_ok and redis_ok
    payload = {
        "status": "ok" if healthy else "degraded",
        "app": settings.app_name,
        "version": settings.app_version,
        "env": settings.app_env,
        "dependencies": {
            "postgres": {"ok": db_ok, "error": db_error},
            "redis": {"ok": redis_ok, "error": redis_error},
        },
    }
    code = status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(content=payload, status_code=code)
