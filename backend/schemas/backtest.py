"""backend.schemas.backtest — Request / response schemas for POST /api/backtest."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class BacktestRequest(BaseModel):
    symbol: str = Field(..., examples=["BTCUSDT", "ETHUSDT"])
    timeframe: str = Field("1h", examples=["15m", "1h", "4h", "1d"])
    start: str = Field(..., examples=["2024-01-01"],
                        description="ISO date string (inclusive)")
    end: str = Field(..., examples=["2024-12-31"],
                      description="ISO date string (inclusive)")
    limit: int = Field(2000, ge=100, le=10000,
                        description="Max bars to pull from the DB")
    initial_capital: float = Field(10_000.0, gt=0)
    commission_bps: float = Field(1.0, ge=0)
    slippage_bps: float = Field(1.0, ge=0)
    save_to_db: bool = Field(True, description="Persist summary to PostgreSQL backtest_results")


class BacktestResponse(BaseModel):
    name: str
    symbol: str
    timeframe: str
    start_date: str | None = None
    end_date: str | None = None
    generated_at: str
    metrics: dict[str, Any]
    bias_report: list[dict[str, Any]]
    config: dict[str, Any]
    total_trades: int
    total_signals: int
    equity_curve: list[dict[str, Any]]  # [{timestamp, equity}, ...]
    trades: list[dict[str, Any]]
