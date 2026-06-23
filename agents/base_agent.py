"""
agents.base_agent — Abstract base class for all Aegis agents.

Every specialized agent (technical, fundamental, sentiment, macro) inherits
from `BaseAgent` and implements `analyze()`. The contract is intentionally
narrow so that the Chief Agent can call every subordinate agent uniformly.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class AgentOutput(BaseModel):
    """Standardized output contract for every agent."""

    agent: str
    symbol: str
    direction: str = Field(..., description="'long' | 'short' | 'flat'")
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


class BaseAgent(ABC):
    """Abstract base class for all Aegis agents.

    Subclasses MUST set `name` and implement `analyze()`. The class is
    async-first because real agents may call external APIs, LLMs, or
    databases.
    """

    name: str = "base"
    description: str = "Abstract base agent — override in subclasses."

    @abstractmethod
    async def analyze(self, symbol: str, **kwargs: Any) -> AgentOutput:
        """Run analysis for `symbol` and return a standardized output."""
        raise NotImplementedError

    @property
    def metadata(self) -> dict[str, str]:
        return {"agent": self.name, "description": self.description, "version": "0.1.0"}

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r}>"
