"""
probability.engine — Probabilistic conviction engine.

Takes a list of `AgentOutput`s (each carrying a direction, a confidence,
and free-form evidence) and produces a single conviction score in [0, 1]
along with an explanation of how the evidence was fused.

Phase 5 implements the concrete fusion model. Candidate approaches:
  - Bayesian opinion pooling
  - Logistic regression on calibrated agent confidences
  - Stacked meta-learner over agent outputs

Today this module ships the interface contract.
"""
from __future__ import annotations

from dataclasses import dataclass

from agents.base_agent import AgentOutput


@dataclass
class ConvictionResult:
    """Output of the probability engine."""

    conviction: float  # 0..1
    direction: str  # 'long' | 'short' | 'flat'
    contributions: dict[str, float]  # agent_name -> contribution weight
    explanation: str


class ProbabilityEngine:
    """Fuse agent outputs into a single probabilistic conviction."""

    name: str = "probability"

    def __init__(self, method: str = "bayesian") -> None:
        self.method = method

    def fuse(self, outputs: list[AgentOutput]) -> ConvictionResult:
        """Fuse a list of agent outputs. Phase 5."""
        raise NotImplementedError("ProbabilityEngine.fuse() lands in Phase 5.")
