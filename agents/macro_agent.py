"""
agents.macro_agent — Top-down macro regime agent.

Tracks macro indicators (rates, DXY, yields, risk-on/off regimes) and
produces a directional bias for each symbol based on macro sensitivity.
Phase 4 implements the concrete indicators and regime classifier.
"""
from __future__ import annotations

from typing import Any

from agents.base_agent import AgentOutput, BaseAgent


class MacroAgent(BaseAgent):
    name = "macro"
    description = "Top-down macro regime classification and bias."

    async def analyze(self, symbol: str, **kwargs: Any) -> AgentOutput:
        return AgentOutput(
            agent=self.name,
            symbol=symbol,
            direction="flat",
            confidence=0.0,
            evidence={"status": "not_implemented"},
            errors=["MacroAgent.analyze() not yet implemented (Phase 4)."],
        )
