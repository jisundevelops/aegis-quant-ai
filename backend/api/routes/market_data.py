"""
backend.api.routes.market_data — Market data endpoints.

Phase 2 will wire these endpoints to the data connectors in `/data`.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from backend.schemas.market_data import OHLCVResponse

router = APIRouter()


@router.get("/ohlcv", response_model=OHLCVResponse)
async def get_ohlcv(
    symbol: str = Query(..., description="Ticker, e.g. 'BTCUSDT' or 'AAPL'"),
    interval: str = Query("1h", description="Bar interval, e.g. '1m','5m','1h','1d'"),
    limit: int = Query(500, ge=1, le=1000),
) -> OHLCVResponse:
    """Fetch OHLCV bars for a symbol.

    Implementation lands in Phase 2 (data connectors).
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Market data connector is wired in Phase 2.",
    )
