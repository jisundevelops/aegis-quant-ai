"""
backend.api.routes.signals — Trading signal endpoints.

Phase 4+ will wire these endpoints to the agent framework + Chief Agent.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from backend.schemas.signals import SignalResponse

router = APIRouter()


@router.get("/latest", response_model=SignalResponse)
async def get_latest_signal(
    symbol: str = Query(..., description="Ticker, e.g. 'BTCUSDT' or 'AAPL'"),
) -> SignalResponse:
    """Return the latest aggregated signal for a symbol."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Signal pipeline is wired in Phase 4 (agents).",
    )
