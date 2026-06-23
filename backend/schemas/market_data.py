"""
backend.schemas.market_data — Pydantic schemas for market data responses.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class OHLCV(BaseModel):
    """A single OHLCV bar."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class OHLCVResponse(BaseModel):
    """Paginated OHLCV response."""

    symbol: str
    interval: str
    source: str = Field(..., description="Connector name, e.g. 'binance'")
    data: list[OHLCV]


class SymbolInfo(BaseModel):
    """Static metadata for a tradable symbol."""

    symbol: str
    exchange: str
    asset_class: str = Field(..., description="crypto | equity | fx | future")
    base_currency: str | None = None
    quote_currency: str | None = None
    tick_size: float | None = None
    lot_size: float | None = None
