"""backend.schemas.analyze — Request / response schemas for POST /api/analyze."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    symbol: str = Field(..., examples=["BTCUSDT", "ETHUSDT"])
    timeframe: str = Field("1h", examples=["15m", "1h", "4h", "1d"])
    limit: int = Field(500, ge=50, le=2000)
    capital: float = Field(10_000.0, gt=0)
    use_feature_cache: bool = Field(True)


class AgentBreakdown(BaseModel):
    bias: str
    confidence: float
    weight: float
    weighted_contribution: float
    reasoning: str


class ScenarioProbabilitiesSchema(BaseModel):
    bull_pct: float
    bear_pct: float
    range_pct: float
    sum_pct: float
    contributions: dict[str, Any] = {}
    explanation: str = ""


class AnalyzeResponse(BaseModel):
    symbol: str
    timeframe: str
    direction: str
    entry_zone: list[float] | None = None
    stop_loss: float | None = None
    take_profit_1: float | None = None
    take_profit_2: float | None = None
    risk_score: float = Field(..., ge=0, le=100)
    confidence_score: float = Field(..., ge=0, le=100)
    reasoning: str
    agent_breakdown: dict[str, AgentBreakdown]
    probabilities: ScenarioProbabilitiesSchema
    trade_plan: dict[str, Any] | None = None
    timestamp: str = ""
