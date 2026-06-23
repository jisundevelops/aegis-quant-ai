"""
risk.limits — Hard risk limits (max drawdown, max leverage, exposure caps).

Loaded from configuration. The risk manager enforces these on every
proposed position. Phase 7 implements the concrete evaluation logic.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RiskLimits:
    """Hard portfolio-level limits."""

    max_portfolio_leverage: float = 1.0
    max_position_pct: float = 0.20
    max_sector_pct: float = 0.40
    max_drawdown_pct: float = 0.15
    daily_var_limit_pct: float = 0.03
    min_cash_buffer_pct: float = 0.05

    def validate(self) -> None:
        """Sanity-check the limits. Phase 7."""
        if not 0 < self.max_position_pct <= 1:
            raise ValueError("max_position_pct must be in (0, 1]")
        if not 0 < self.max_drawdown_pct <= 1:
            raise ValueError("max_drawdown_pct must be in (0, 1]")
