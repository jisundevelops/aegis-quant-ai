"""
risk.manager — Central risk manager.

Takes a conviction score + portfolio state + risk limits and produces a
sized, risk-bounded position proposal. Phase 7 implements the evaluation.
"""
from __future__ import annotations

from dataclasses import dataclass

from risk.limits import RiskLimits


@dataclass
class PositionProposal:
    """Output of the risk manager."""

    symbol: str
    target_quantity: float
    conviction: float
    sizing_method: str
    limits_checked: bool
    rejection_reason: str | None = None


class RiskManager:
    """Convert conviction into a sized, risk-bounded position proposal."""

    def __init__(self, limits: RiskLimits | None = None) -> None:
        self.limits = limits or RiskLimits()

    def evaluate(
        self,
        symbol: str,
        conviction: float,
        capital: float,
        current_positions: dict[str, float] | None = None,
    ) -> PositionProposal:
        """Evaluate a proposed position. Phase 7."""
        raise NotImplementedError("RiskManager.evaluate() lands in Phase 7.")
