"""
chief.orchestrator — Chief Agent orchestration logic.

The Chief Agent:
  1. Fans out to all subordinate agents concurrently.
  2. Collects their `AgentOutput`s.
  3. Forwards the aggregated evidence to the Probability Engine.
  4. Returns a final `SignalResponse` ready for the risk manager.

Phase 5 implements the concrete aggregation; today this module ships the
interface and stub.
"""
from __future__ import annotations

from typing import Any

from agents.base_agent import AgentOutput, BaseAgent
from backend.schemas.signals import SignalResponse


class ChiefAgent:
    """Orchestrates subordinate agents and aggregates their outputs."""

    name: str = "chief"

    def __init__(self, agents: list[BaseAgent] | None = None) -> None:
        self.agents: list[BaseAgent] = list(agents or [])

    def register(self, agent: BaseAgent) -> "ChiefAgent":
        self.agents.append(agent)
        return self

    async def run(self, symbol: str, **kwargs: Any) -> SignalResponse:
        """Run all subordinate agents and aggregate. Phase 5."""
        raise NotImplementedError("ChiefAgent.run() lands in Phase 5.")

    async def _fan_out(self, symbol: str, **kwargs: Any) -> list[AgentOutput]:
        """Concurrently call every registered agent. Phase 5."""
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"<ChiefAgent agents={[a.name for a in self.agents]}>"
