"""
agents.sentiment_agent — News + social sentiment agent.

Consumes news APIs and social feeds (Twitter/X, Reddit) and produces a
sentiment score in [-1, +1] which is then mapped to a directional signal.
Phase 4 wires the concrete NLP / LLM pipeline.
"""
from __future__ import annotations

from typing import Any

from agents.base_agent import AgentOutput, BaseAgent


class SentimentAgent(BaseAgent):
    name = "sentiment"
    description = "News and social sentiment scoring via NLP / LLM."

    async def analyze(self, symbol: str, **kwargs: Any) -> AgentOutput:
        return AgentOutput(
            agent=self.name,
            symbol=symbol,
            direction="flat",
            confidence=0.0,
            evidence={"status": "not_implemented"},
            errors=["SentimentAgent.analyze() not yet implemented (Phase 4)."],
        )
