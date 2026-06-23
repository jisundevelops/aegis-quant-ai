"""
scripts.verify_db — Live connectivity check for PostgreSQL + Redis.

Verifies that the credentials in .env actually work. Run:

    python scripts/verify_db.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Ensure repo root is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# The sandbox may have its own DATABASE_URL / REDIS_URL set in the parent
# environment. Force the .env file in this repo to take precedence by
# clearing any inherited values before importing `config`.
for _k in ("DATABASE_URL", "REDIS_URL"):
    os.environ.pop(_k, None)

# Bust the settings cache so a fresh Settings() is built from .env only.
try:
    from config.settings import get_settings
    get_settings.cache_clear()
except Exception:
    pass

from sqlalchemy import text


async def check_postgres() -> tuple[bool, str]:
    try:
        from database.connection import async_session_ctx, close_all, get_async_engine
        engine = get_async_engine()
        async with async_session_ctx() as session:
            row = (await session.execute(text("SELECT 1 AS one, NOW() AS ts"))).one()
            version_row = (await session.execute(text("SELECT version()"))).scalar()
        return True, f"OK  ({version_row[:60]}...)"
    except Exception as exc:  # noqa: BLE001
        return False, f"FAIL ({type(exc).__name__}: {exc})"
    finally:
        try:
            await close_all()
        except Exception:
            pass


async def check_redis() -> tuple[bool, str]:
    try:
        from database.connection import close_all, get_redis
        r = get_redis()
        pong = await r.ping()
        info = await r.info("server")
        ver = info.get("redis_version", "?")
        return bool(pong), f"OK  (redis_version={ver})"
    except Exception as exc:  # noqa: BLE001
        return False, f"FAIL ({type(exc).__name__}: {exc})"
    finally:
        try:
            await close_all()
        except Exception:
            pass


async def main() -> int:
    print("=" * 60)
    print("Aegis Quant AI — Live DB connectivity check")
    print("=" * 60)

    print("\n[1/2] PostgreSQL ...")
    ok, msg = await check_postgres()
    print(f"      {msg}")
    pg_ok = ok

    print("\n[2/2] Redis ........")
    ok, msg = await check_redis()
    print(f"      {msg}")
    rd_ok = ok

    print("\n" + "=" * 60)
    print("RESULT:", "ALL GREEN" if (pg_ok and rd_ok) else "DEGRADED")
    print("=" * 60)
    return 0 if (pg_ok and rd_ok) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
