#!/usr/bin/env python
"""
scripts.fetch_data — Manually fetch market data and populate PostgreSQL.

Use this script when:
  - The market_data table is empty (fresh deploy)
  - You want to backfill historical data before starting the scheduler
  - The scheduler is disabled but you need data for /api/analyze

Usage:
    python scripts/fetch_data.py                # fetch all (Binance + Yahoo)
    python scripts/fetch_data.py --binance      # fetch Binance only
    python scripts/fetch_data.py --yahoo        # fetch Yahoo only
    python scripts/fetch_data.py --status       # show market_data table status

Environment variables required:
    DATABASE_URL  — PostgreSQL connection string
    REDIS_URL     — Redis connection string (for caching)
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Ensure repo root is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def fetch_all(binance: bool, yahoo: bool) -> None:
    """Run the fetch_now() function from the scheduler."""
    from data.scheduler import fetch_now
    results = await fetch_now(binance=binance, yahoo=yahoo)
    total = sum(results.values())
    print(f"\n✅ Fetch complete: {total} rows stored across {len(results)} pairs")
    for key, count in sorted(results.items()):
        print(f"   {key}: {count} rows")


async def show_status() -> None:
    """Show the current state of the market_data table."""
    from sqlalchemy import func, select
    from database.connection import async_session_ctx
    from database.models import MarketData

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

    print(f"\n📊 market_data table status:")
    print(f"   Total rows: {total}")
    if rows:
        print(f"   Breakdown:")
        for symbol, timeframe, count in rows:
            print(f"     {symbol:12s} {timeframe:4s}  {count} rows")
    else:
        print("   ⚠️  Table is EMPTY — run with --binance or --yahoo to fetch")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch market data into PostgreSQL")
    parser.add_argument("--binance", action="store_true", help="Fetch Binance data only")
    parser.add_argument("--yahoo", action="store_true", help="Fetch Yahoo data only")
    parser.add_argument("--status", action="store_true", help="Show market_data table status")
    args = parser.parse_args()

    if args.status:
        asyncio.run(show_status())
        return 0

    # If neither flag is set, fetch both
    do_binance = args.binance or (not args.yahoo and not args.status)
    do_yahoo = args.yahoo or (not args.binance and not args.status)
    if not do_binance and not do_yahoo:
        do_binance = do_yahoo = True

    print(f"Fetching data: Binance={do_binance}, Yahoo={do_yahoo}")
    asyncio.run(fetch_all(do_binance, do_yahoo))
    return 0


if __name__ == "__main__":
    sys.exit(main())
