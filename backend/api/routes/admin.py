"""
backend.api.routes.admin — Admin endpoints for manual data operations.

POST /api/admin/fetch-data   — Trigger an immediate Binance + Yahoo fetch
GET  /api/admin/data-status  — Show what's in the market_data table
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import func, select

from database.connection import async_session_ctx
from database.models import MarketData

router = APIRouter()


class FetchDataResponse(BaseModel):
    """Response from POST /api/admin/fetch-data."""

    status: str
    rows_stored: dict[str, int]
    total_rows: int
    message: str


class DataStatusResponse(BaseModel):
    """Response from GET /api/admin/data-status."""

    total_rows: int
    by_symbol: dict[str, dict[str, int]]  # {symbol: {timeframe: count}}


@router.post("/admin/fetch-data", response_model=FetchDataResponse,
             status_code=status.HTTP_200_OK)
async def fetch_data_now() -> FetchDataResponse:
    """Trigger an immediate data fetch from Binance + Yahoo.

    Use this endpoint when the market_data table is empty (e.g. after a
    fresh deploy) and you don't want to wait for the scheduler's next
    cron tick.
    """
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
    """Show the current state of the market_data table.

    Returns total row count + breakdown by symbol and timeframe.
    """
    try:
        async with async_session_ctx() as session:
            # Total count
            total_stmt = select(func.count()).select_from(MarketData)
            total = (await session.execute(total_stmt)).scalar() or 0

            # Breakdown by symbol + timeframe
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

        return DataStatusResponse(
            total_rows=int(total),
            by_symbol=by_symbol,
        )
    except Exception as exc:
        logger.exception("Data status query failed: {}", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Data status query failed: {exc}",
        ) from exc
