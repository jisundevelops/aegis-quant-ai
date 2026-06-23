"""
backtest.portfolio — Portfolio state tracking during a backtest.

Maintains cash, positions, and equity over time. Phase 6 implements the
event handlers; this module ships the dataclass today.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class Position:
    """A single open position."""

    symbol: str
    quantity: float
    avg_price: float
    side: str = "long"  # 'long' | 'short'


@dataclass
class Portfolio:
    """Mutable portfolio state for the backtest engine."""

    cash: float
    positions: dict[str, Position] = field(default_factory=dict)
    equity_history: list[tuple[pd.Timestamp, float]] = field(default_factory=list)

    @property
    def equity(self) -> float:
        """Current mark-to-market equity. Phase 6 implements mark-to-market."""
        return self.cash

    def apply_fill(self, fill: dict) -> None:
        """Apply a fill to the portfolio. Phase 6."""
        raise NotImplementedError
