"""
backtest.metrics — Performance metrics for backtest results.

Sharpe, Sortino, max drawdown, Calmar, win rate, profit factor, etc.
Phase 6 implements the concrete formulas.
"""
from __future__ import annotations

import pandas as pd


def sharpe_ratio(returns: pd.Series, risk_free: float = 0.0, periods: int = 252) -> float:
    """Annualized Sharpe ratio. Phase 6."""
    raise NotImplementedError


def sortino_ratio(returns: pd.Series, risk_free: float = 0.0, periods: int = 252) -> float:
    """Annualized Sortino ratio. Phase 6."""
    raise NotImplementedError


def max_drawdown(equity: pd.Series) -> float:
    """Maximum drawdown as a negative fraction (e.g. -0.25 = -25%). Phase 6."""
    raise NotImplementedError


def calmar_ratio(returns: pd.Series, equity: pd.Series, periods: int = 252) -> float:
    """Annualized return / max drawdown. Phase 6."""
    raise NotImplementedError


def win_rate(trades: pd.DataFrame) -> float:
    """Fraction of profitable trades. Phase 6."""
    raise NotImplementedError


def profit_factor(trades: pd.DataFrame) -> float:
    """Gross profit / gross loss. Phase 6."""
    raise NotImplementedError


def compute_all(equity: pd.Series, trades: pd.DataFrame, risk_free: float = 0.0) -> dict:
    """Compute the full metrics dictionary for a backtest. Phase 6."""
    raise NotImplementedError
