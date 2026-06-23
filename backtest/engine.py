"""
backtest.engine — Event-driven backtesting engine.

Consumes signals + prices and produces a `BacktestResult`. Phase 6
implements the core event loop; this module ships the dataclasses and
interface today.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class BacktestConfig:
    """Configuration for a single backtest run."""

    initial_capital: float = 100_000.0
    commission_bps: float = 1.0  # 1 basis point per side
    slippage_bps: float = 1.0
    max_leverage: float = 1.0
    shorting_allowed: bool = True
    risk_free_rate: float = 0.0


@dataclass
class BacktestResult:
    """Output of a backtest run."""

    equity_curve: pd.Series
    trades: pd.DataFrame
    positions: pd.DataFrame
    metrics: dict = field(default_factory=dict)
    config: BacktestConfig | None = None


class BacktestEngine:
    """Event-driven backtester."""

    def __init__(self, config: BacktestConfig | None = None) -> None:
        self.config = config or BacktestConfig()

    def run(
        self,
        prices: pd.DataFrame,
        signals: pd.DataFrame,
    ) -> BacktestResult:
        """Run a backtest. Implementation lands in Phase 6."""
        raise NotImplementedError("BacktestEngine.run() lands in Phase 6.")
