"""
probability.engine — Backward-compatible re-export shim.

Phase 1 shipped this filename with a stub class. Phase 6 moved the real
implementation to `probability.probability_engine`. This module re-exports
the new classes so existing imports continue to work.
"""
from __future__ import annotations

from dataclasses import dataclass

from probability.probability_engine import (
    ProbabilityEngine,
    ScenarioProbabilities,
)


@dataclass
class ConvictionResult:
    """Phase 1 output contract. Use ScenarioProbabilities in new code."""

    conviction: float
    direction: str
    contributions: dict[str, float]
    explanation: str


__all__ = ["ProbabilityEngine", "ScenarioProbabilities", "ConvictionResult"]
