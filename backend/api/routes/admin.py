"""
backend.api.routes.admin — Admin endpoints for diagnostics + manual data operations.

Endpoints:
  POST /api/admin/fetch-data    — Trigger immediate Binance + Yahoo fetch
  GET  /api/admin/data-status   — Show market_data table contents
  GET  /api/admin/diagnose      — Full system diagnostic (DB, Redis, Binance, env vars)
"""
from __future__ import annotations

import socket
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy import text as sql_text

from config import settings
from database.connection import async_session_ctx
from database.models import MarketData

router = APIRouter()


class FetchDataResponse(BaseModel):
    status: str
    rows_stored: dict[str, int]
    total_rows: int
    message: str


class DataStatusResponse(BaseModel):
    total_rows: int
    by_symbol: dict[str, dict[str, int]]


class DiagnosticResponse(BaseModel):
    timestamp: str
    environment: dict
    database: dict
    redis: dict
    binance: dict
    summary: str
    overall_status: str


def _mask_url(url: str) -> str:
    """Mask the password in a URL for safe logging."""
    if not url:
        return "(not set)"
    # Show scheme + host but mask password
    if "@" in url:
        if "://" in url:
            scheme_part = url.split("://")[0]
            rest = url.split("://", 1)[1]
        else:
            scheme_part = ""
            rest = url
        creds, host = rest.split("@", 1)
        if ":" in creds:
            user = creds.split(":")[0]
            return f"{scheme_part}://{user}:***@{host}" if scheme_part else f"{user}:***@{host}"
        return f"{scheme_part}://***@{host}" if scheme_part else f"***@{host}"
    return url


def _check_dns(hostname: str) -> dict:
    """Check if a hostname resolves."""
    try:
        ip = socket.gethostbyname(hostname)
        return {"ok": True, "ip": ip}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def _check_tcp(host: str, port: int, timeout: float = 5.0) -> dict:
    """Check if a TCP port is reachable."""
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


@router.post("/admin/fetch-data", response_model=FetchDataResponse,
             status_code=status.HTTP_200_OK)
async def fetch_data_now() -> FetchDataResponse:
    """Trigger an immediate data fetch from Binance + Yahoo."""
    logger.info("POST /api/admin/fetch-data — manual fetch triggered")
    try:
        from data.scheduler import fetch_now
        results = await fetch_now(binance=True, yahoo=True)
        total = sum(results.values())
        return FetchDataResponse(
            status="ok",
            rows_stored=results,
            total_rows=total,
            message=f"Fetched {total} rows across {len(results)} symbol/timeframe pairs.",
        )
    except Exception as exc:
        logger.exception("Manual fetch failed: {}", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Manual fetch failed: {exc}",
        ) from exc


@router.get("/admin/data-status", response_model=DataStatusResponse,
            status_code=status.HTTP_200_OK)
async def get_data_status() -> DataStatusResponse:
    """Show the current state of the market_data table."""
    try:
        async with async_session_ctx() as session:
            total_stmt = select(func.count()).select_from(MarketData)
            total = (await session.execute(total_stmt)).scalar() or 0
            stmt = (
                select(
                    MarketData.symbol,
                    MarketData.timeframe,
                    func.count().label("cnt"),
                )
                .group_by(MarketData.symbol, MarketData.timeframe)
                .order_by(MarketData.symbol, MarketData.timeframe)
            )
            rows = (await session.execute(stmt)).all()
        by_symbol: dict[str, dict[str, int]] = {}
        for symbol, timeframe, count in rows:
            by_symbol.setdefault(symbol, {})[timeframe] = int(count)
        return DataStatusResponse(total_rows=int(total), by_symbol=by_symbol)
    except Exception as exc:
        logger.exception("Data status query failed: {}", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Data status query failed: {exc}",
        ) from exc


@router.get("/admin/diagnose", response_model=DiagnosticResponse,
            status_code=status.HTTP_200_OK)
async def diagnose() -> DiagnosticResponse:
    """Full system diagnostic — checks DB, Redis, Binance, and env vars.

    Use this endpoint when something is broken. It reports:
    - Whether DATABASE_URL is set and points to PostgreSQL (not a file)
    - Whether the DB host resolves in DNS
    - Whether the DB port is reachable via TCP
    - Whether a test query (SELECT 1) succeeds
    - Same checks for Redis
    - Whether Binance API is reachable
    """
    ts = datetime.now(timezone.utc).isoformat()
    db_result: dict = {}
    redis_result: dict = {}
    binance_result: dict = {}
    env_result: dict = {}
    issues: list[str] = []

    # ── Environment variables ──────────────────────────────────────
    env_result = {
        "DATABASE_URL": _mask_url(settings.postgres_dsn),
        "REDIS_URL": _mask_url(settings.effective_redis_url),
        "SCHEDULER_ENABLED": settings.scheduler_enabled,
        "APP_ENV": settings.app_env,
    }

    # Check if DATABASE_URL looks valid
    dsn = settings.postgres_dsn
    if not dsn:
        issues.append("DATABASE_URL is not set. Set it in Render dashboard.")
        db_result = {"ok": False, "error": "DATABASE_URL not set"}
    elif dsn.startswith("file:"):
        issues.append(
            f"DATABASE_URL points to a local file ({dsn}). "
            "It must be a PostgreSQL URL (postgresql+asyncpg://...). "
            "Set DATABASE_URL in Render dashboard to your Supabase URL."
        )
        db_result = {"ok": False, "error": "DATABASE_URL is a file, not PostgreSQL"}
    elif not dsn.startswith("postgresql"):
        issues.append(
            f"DATABASE_URL has wrong scheme: {dsn[:30]}. "
            "Must start with 'postgresql+asyncpg://'."
        )
        db_result = {"ok": False, "error": "Wrong URL scheme"}
    else:
        # Parse the URL to extract host + port
        db_result = await _diagnose_database(dsn, issues)

    # ── Redis ──────────────────────────────────────────────────────
    redis_url = settings.effective_redis_url
    if not redis_url:
        issues.append("REDIS_URL is not set.")
        redis_result = {"ok": False, "error": "REDIS_URL not set"}
    else:
        redis_result = await _diagnose_redis(redis_url, issues)

    # ── Binance ────────────────────────────────────────────────────
    binance_result = _diagnose_binance(issues)

    # ── Summary ────────────────────────────────────────────────────
    db_ok = db_result.get("ok", False)
    redis_ok = redis_result.get("ok", False)
    binance_ok = binance_result.get("ok", False)

    if db_ok and redis_ok and binance_ok:
        overall = "ok"
        summary = "All systems operational."
    elif not db_ok:
        overall = "critical"
        summary = "Database connection failed. /api/analyze will return 404."
    elif not redis_ok:
        overall = "degraded"
        summary = "Redis connection failed. Caching disabled but API works."
    else:
        overall = "degraded"
        summary = "Some systems degraded."

    if issues:
        summary += " Issues: " + "; ".join(issues)

    return DiagnosticResponse(
        timestamp=ts,
        environment=env_result,
        database=db_result,
        redis=redis_result,
        binance=binance_result,
        summary=summary,
        overall_status=overall,
    )


async def _diagnose_database(dsn: str, issues: list[str]) -> dict:
    """Test database connectivity step by step."""
    result: dict = {"url": _mask_url(dsn)}

    # Extract host + port from DSN
    try:
        from urllib.parse import urlparse
        parsed = urlparse(dsn.replace("postgresql+asyncpg://", "postgresql://"))
        host = parsed.hostname or ""
        port = parsed.port or 5432
        result["host"] = host
        result["port"] = port
    except Exception as e:
        result["ok"] = False
        result["error"] = f"Failed to parse DSN: {e}"
        issues.append(f"DATABASE_URL is malformed: {e}")
        return result

    # 1. DNS check
    dns = _check_dns(host)
    result["dns"] = dns
    if not dns["ok"]:
        result["ok"] = False
        result["error"] = f"DNS resolution failed for {host}: {dns['error']}"
        issues.append(
            f"Cannot resolve database hostname '{host}'. "
            "Check if your Supabase project URL is correct."
        )
        return result

    # 2. TCP check
    tcp = _check_tcp(host, port)
    result["tcp"] = tcp
    if not tcp["ok"]:
        result["ok"] = False
        result["error"] = f"TCP connection failed to {host}:{port}: {tcp['error']}"
        issues.append(
            f"Cannot reach database at {host}:{port}. "
            "This is a network issue — Render cannot route to Supabase. "
            "Possible causes: (1) Supabase project is paused (free tier auto-pauses "
            "after 7 days of inactivity). (2) Supabase is blocking Render's IP. "
            "(3) Wrong port. Try the Supabase connection pooler URL instead."
        )
        return result

    # 3. Actual query test
    try:
        async with async_session_ctx() as session:
            await session.execute(sql_text("SELECT 1"))
        result["ok"] = True
        result["query"] = "SELECT 1 succeeded"
    except Exception as e:
        result["ok"] = False
        result["error"] = f"Query failed: {type(e).__name__}: {e}"
        issues.append(
            f"Database query failed: {e}. "
            "DNS and TCP are OK, but the query failed. "
            "Check if the password is correct (remember to URL-encode @ as %40)."
        )

    return result


async def _diagnose_redis(redis_url: str, issues: list[str]) -> dict:
    """Test Redis connectivity."""
    result: dict = {"url": _mask_url(redis_url)}

    try:
        from urllib.parse import urlparse
        parsed = urlparse(redis_url)
        host = parsed.hostname or ""
        port = parsed.port or 6379
        result["host"] = host
        result["port"] = port
    except Exception as e:
        result["ok"] = False
        result["error"] = f"Failed to parse URL: {e}"
        return result

    # DNS check
    dns = _check_dns(host)
    result["dns"] = dns
    if not dns["ok"]:
        result["ok"] = False
        result["error"] = f"DNS failed: {dns['error']}"
        issues.append(f"Cannot resolve Redis hostname '{host}'.")
        return result

    # TCP check
    tcp = _check_tcp(host, port)
    result["tcp"] = tcp
    if not tcp["ok"]:
        result["ok"] = False
        result["error"] = f"TCP failed: {tcp['error']}"
        issues.append(
            f"Cannot reach Redis at {host}:{port}. "
            "Check your Upstash URL and TLS setting (rediss:// vs redis://)."
        )
        return result

    # Ping test
    try:
        from database.connection import get_redis
        r = get_redis()
        await r.ping()
        result["ok"] = True
        result["ping"] = "PONG"
    except Exception as e:
        result["ok"] = False
        result["error"] = f"Ping failed: {type(e).__name__}: {e}"
        issues.append(f"Redis ping failed: {e}")

    return result


def _diagnose_binance(issues: list[str]) -> dict:
    """Test Binance API reachability."""
    result: dict = {"endpoint": "api.binance.com"}
    host = "api.binance.com"

    # DNS check
    dns = _check_dns(host)
    result["dns"] = dns
    if not dns["ok"]:
        result["ok"] = False
        result["error"] = f"DNS failed: {dns['error']}"
        issues.append("Cannot resolve api.binance.com — Binance data fetch will fail.")
        return result

    # TCP check (port 443 for HTTPS)
    tcp = _check_tcp(host, 443)
    result["tcp"] = tcp
    if not tcp["ok"]:
        result["ok"] = False
        result["error"] = f"TCP failed: {tcp['error']}"
        issues.append("Cannot reach Binance API — data scheduler will fail.")
        return result

    result["ok"] = True
    return result
