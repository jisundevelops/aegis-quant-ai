"""
probability.probability_engine — Scenario probability engine.

Takes a list of AgentSignal objects (Phase 5 contract: bias ∈
{Bullish, Bearish, Neutral}, confidence 0..100, reasoning) plus their
Chief-Agent weights, and produces three scenario probabilities:

  - Bull scenario probability   (%)
  - Bear scenario probability   (%)
  - Range scenario probability  (%)

These three are guaranteed to sum to exactly 100% (any rounding residue
is added to the largest bucket).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agents.base_agent import AgentSignal


@dataclass
class ScenarioProbabilities:
    """Bull / Bear / Range scenario probabilities. Sum to 100.0."""

    bull_pct: float
    bear_pct: float
    range_pct: float
    contributions: dict[str, dict[str, float]] = field(default_factory=dict)
    explanation: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "bull_pct": round(self.bull_pct, 2),
            "bear_pct": round(self.bear_pct, 2),
            "range_pct": round(self.range_pct, 2),
            "sum_pct": round(self.bull_pct + self.bear_pct + self.range_pct, 2),
            "contributions": self.contributions,
            "explanation": self.explanation,
        }

    def __post_init__(self) -> None:
        total = self.bull_pct + self.bear_pct + self.range_pct
        if total <= 0:
            self.bull_pct = self.bear_pct = self.range_pct = 100.0 / 3.0
            return
        self.bull_pct *= 100.0 / total
        self.bear_pct *= 100.0 / total
        self.range_pct *= 100.0 / total
        drift = 100.0 - (self.bull_pct + self.bear_pct + self.range_pct)
        if abs(drift) >= 0.005:
            buckets = [("bull_pct", self.bull_pct),
                       ("bear_pct", self.bear_pct),
                       ("range_pct", self.range_pct)]
            biggest = max(buckets, key=lambda b: b[1])[0]
            setattr(self, biggest, getattr(self, biggest) + drift)


class ProbabilityEngine:
    """Convert agent votes into three scenario probabilities."""

    name: str = "probability"

    def __init__(self, method: str = "bayesian", disagreement_boost: float = 0.15) -> None:
        self.method = method
        self.disagreement_boost = disagreement_boost

    def compute(
        self,
        signals: list[AgentSignal],
        weights: dict[str, float] | None = None,
    ) -> ScenarioProbabilities:
        if not signals:
            return ScenarioProbabilities(
                bull_pct=100 / 3, bear_pct=100 / 3, range_pct=100 / 3,
                explanation="No signals provided — defaulting to uniform 33/33/33.",
            )

        if weights is None:
            weights = {s.agent: 1.0 / len(signals) for s in signals}

        bull_total = 0.0
        bear_total = 0.0
        range_total = 0.0
        contributions: dict[str, dict[str, float]] = {}

        for sig in signals:
            w = float(weights.get(sig.agent, 0.0))
            c = float(sig.confidence)
            if sig.bias == "Bullish":
                bull_total += w * c
            elif sig.bias == "Bearish":
                bear_total += w * c
            else:
                range_total += w * c
            contributions[sig.agent] = {
                "weight": round(w, 4),
                "bias": sig.bias,
                "confidence": round(c, 2),
                "weighted_contribution": round(w * c, 2),
            }

        if bull_total > 0 and bear_total > 0:
            smaller = min(bull_total, bear_total)
            boost = smaller * self.disagreement_boost
            if bull_total >= bear_total:
                bear_total -= boost
            else:
                bull_total -= boost
            range_total += boost

        total = bull_total + bear_total + range_total
        if total <= 0:
            return ScenarioProbabilities(
                bull_pct=100 / 3, bear_pct=100 / 3, range_pct=100 / 3,
                contributions=contributions,
                explanation="All agents had zero confidence — defaulting to 33/33/33.",
            )

        explanation = self._build_explanation(
            bull_total, bear_total, range_total, contributions
        )

        return ScenarioProbabilities(
            bull_pct=bull_total,
            bear_pct=bear_total,
            range_pct=range_total,
            contributions=contributions,
            explanation=explanation,
        )

    def _build_explanation(
        self,
        bull: float,
        bear: float,
        range_: float,
        contributions: dict[str, dict[str, float]],
    ) -> str:
        dominant = "bull" if bull >= max(bear, range_) else \
                   ("bear" if bear >= range_ else "range")
        parts = [
            f"Scenario split: Bull {bull:.1f}% / Bear {bear:.1f}% / Range {range_:.1f}%.",
            f"Dominant scenario: {dominant}.",
            "Per-agent contributions:",
        ]
        for name, c in contributions.items():
            parts.append(
                f"  - {name}: weight={c['weight']:.2f}, bias={c['bias']}, "
                f"confidence={c['confidence']:.1f}, contribution={c['weighted_contribution']:.2f}"
            )
        return "\n".join(parts)


__all__ = ["ProbabilityEngine", "ScenarioProbabilities"]
