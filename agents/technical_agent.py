"""
agents.technical_agent — Indicator-based technical analysis agent.

Consumes OHLCV from the data layer, computes indicators via the feature
engine, and emits a directional signal with confidence. Full implementation
lands in Phase 4.
"""
from __future__ import annotations

from typing import Any

from agents.base_agent import AgentOutput, BaseAgent


class TechnicalAgent(BaseAgent):
    name = "technical"
    description = "Indicator-driven technical analysis (RSI, MACD, EMA, ATR)."

    async def analyze(self, symbol: str, **kwargs: Any) -> AgentOutput:
        """Placeholder — Phase 4 will implement the full pipeline."""
        return AgentOutput(
            agent=self.name,
            symbol=symbol,
            direction="flat",
            confidence=0.0,
            evidence={"status": "not_implemented"},
            errors=["TechnicalAgent.analyze() not yet implemented (Phase 4)."],
        )
