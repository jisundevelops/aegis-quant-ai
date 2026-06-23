"""
agents.fundamental_agent — On-chain + balance-sheet fundamental agent.

For crypto: on-chain metrics (active addresses, exchange flows, supply).
For equities: balance-sheet + cash-flow ratios. Phase 4 implements the
concrete data sources and scoring.
"""
from __future__ import annotations

from typing import Any

from agents.base_agent import AgentOutput, BaseAgent


class FundamentalAgent(BaseAgent):
    name = "fundamental"
    description = "On-chain and balance-sheet fundamental scoring."

    async def analyze(self, symbol: str, **kwargs: Any) -> AgentOutput:
        return AgentOutput(
            agent=self.name,
            symbol=symbol,
            direction="flat",
            confidence=0.0,
            evidence={"status": "not_implemented"},
            errors=["FundamentalAgent.analyze() not yet implemented (Phase 4)."],
        )
