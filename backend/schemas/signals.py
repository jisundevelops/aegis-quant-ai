"""
backend.schemas.signals — Pydantic schemas for trading signals.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Direction = Literal["long", "short", "flat"]


class AgentSignal(BaseModel):
    """A signal produced by a single agent."""

    agent: str = Field(..., description="Agent name, e.g. 'technical'")
    symbol: str
    direction: Direction
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence: dict = Field(default_factory=dict)
    timestamp: datetime


class SignalResponse(BaseModel):
    """Aggregated signal produced by the Chief Agent."""

    symbol: str
    direction: Direction
    conviction: float = Field(..., ge=0.0, le=1.0, description="Probability-engine output")
    contributors: list[AgentSignal] = Field(default_factory=list)
    timestamp: datetime
    metadata: dict = Field(default_factory=dict)
