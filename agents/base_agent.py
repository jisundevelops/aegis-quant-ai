"""
agents.base_agent — Abstract base class + output schemas for all Aegis agents.

Backward compatibility:
  - Phase 1's `AgentOutput` (direction long/short/flat, confidence 0..1) is
    preserved for the Chief Agent / Probability Engine stubs.
  - Phase 5 adds `AgentSignal` (bias Bullish/Bearish/Neutral, confidence
    0..100, reasoning string) — the new canonical contract for all
    specialized analysis agents.

Phase 5 agents inherit from `BaseAgent` and return `AgentSignal` (or a
subclass) from `analyze()`. The runtime return type is not enforced, so
this works cleanly without breaking Phase 1's static contract.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel, Field

# --------------------------------------------------------------------
# Phase 1 output contract (kept for backward compat)
# --------------------------------------------------------------------
class AgentOutput(BaseModel):
    """Phase 1 output contract. Kept for Chief Agent / Probability Engine."""

    agent: str
    symbol: str
    direction: str = Field(..., description="'long' | 'short' | 'flat'")
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------
# Phase 5 output contract (canonical for all specialized agents)
# --------------------------------------------------------------------
Bias = Literal["Bullish", "Bearish", "Neutral"]


class AgentSignal(BaseModel):
    """Phase 5 standardized agent output.

    Fields
    ------
    agent       : agent name (matches BaseAgent.name)
    symbol      : ticker analyzed
    bias        : 'Bullish' | 'Bearish' | 'Neutral'
    confidence  : 0..100  (NOT 0..1 — Phase 5 spec)
    reasoning   : human-readable explanation
    evidence    : structured key-value evidence for downstream consumers
    """

    agent: str
    symbol: str
    bias: Bias = "Neutral"
    confidence: float = Field(default=50.0, ge=0.0, le=100.0)
    reasoning: str = ""
    evidence: dict[str, Any] = Field(default_factory=dict)

    @property
    def direction(self) -> str:
        """Map bias to Phase 1's direction enum for Chief Agent compat."""
        return {"Bullish": "long", "Bearish": "short", "Neutral": "flat"}[self.bias]

    @property
    def confidence_01(self) -> float:
        """Confidence rescaled to [0, 1] for Phase 1 consumers."""
        return self.confidence / 100.0


# --------------------------------------------------------------------
# Base agent
# --------------------------------------------------------------------
class BaseAgent(ABC):
    """Abstract base class for all Aegis agents.

    Subclasses MUST set `name` and implement `analyze()`. The class is
    async-first because real agents may call external APIs, LLMs, or
    databases.
    """

    name: str = "base"
    description: str = "Abstract base agent — override in subclasses."

    @abstractmethod
    async def analyze(self, symbol: str, **kwargs: Any) -> AgentSignal:
        """Run analysis for `symbol` and return a standardized signal."""
        raise NotImplementedError

    @property
    def metadata(self) -> dict[str, str]:
        return {"agent": self.name, "description": self.description, "version": "0.1.0"}

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r}>"


__all__ = ["BaseAgent", "AgentOutput", "AgentSignal", "Bias"]
