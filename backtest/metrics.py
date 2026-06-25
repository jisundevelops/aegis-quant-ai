"""
backtest.metrics — Performance metrics for backtest results.

All functions are pure (no side effects) and operate on standard
pandas Series / DataFrame objects.

Metric list (Phase 7 spec):
  - Win Rate             fraction of profitable trades
  - Profit Factor        gross profit / gross loss
  - Sharpe Ratio         annualized mean return / std return
  - Sortino Ratio        annualized mean return / downside std
  - Calmar Ratio         annualized return / max drawdown
  - Max Drawdown         worst peak-to-trough decline (negative fraction)
  - Expectancy           expected $ per trade = win_rate*avg_win - loss_rate*avg_loss
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# --------------------------------------------------------------------
# Individual metric functions
# --------------------------------------------------------------------
def sharpe_ratio(
    returns: pd.Series, risk_free: float = 0.0, periods: int = 252
) -> float:
    """Annualized Sharpe ratio.

    Parameters
    ----------
    returns    : per-bar returns (decimal, e.g. 0.01 = 1%)
    risk_free  : annualized risk-free rate (decimal)
    periods    : number of bars per year (252 daily, 252*24 hourly, etc.)
    """
    if returns is None or returns.empty:
        return 0.0
    r = returns.dropna()
    if len(r) < 2:
        return 0.0
    rf_per_bar = risk_free / periods
    excess = r - rf_per_bar
    std = excess.std(ddof=1)
    if std == 0 or np.isnan(std):
        return 0.0
    return float(np.sqrt(periods) * excess.mean() / std)


def sortino_ratio(
    returns: pd.Series, risk_free: float = 0.0, periods: int = 252
) -> float:
    """Annualized Sortino ratio (uses downside deviation only)."""
    if returns is None or returns.empty:
        return 0.0
    r = returns.dropna()
    if len(r) < 2:
        return 0.0
    rf_per_bar = risk_free / periods
    excess = r - rf_per_bar
    downside = excess[excess < 0]
    if downside.empty:
        return 0.0
    downside_std = np.sqrt((downside ** 2).mean())
    if downside_std == 0 or np.isnan(downside_std):
        return 0.0
    return float(np.sqrt(periods) * excess.mean() / downside_std)


def max_drawdown(equity: pd.Series) -> float:
    """Maximum drawdown as a negative fraction (e.g. -0.25 = -25%).

    Returns 0.0 if the equity curve never declines.
    """
    if equity is None or equity.empty:
        return 0.0
    e = equity.dropna()
    if len(e) < 2:
        return 0.0
    running_max = e.cummax()
    drawdown = (e - running_max) / running_max
    mdd = drawdown.min()
    if np.isnan(mdd):
        return 0.0
    return float(mdd)


def calmar_ratio(
    returns: pd.Series, equity: pd.Series, periods: int = 252
) -> float:
    """Annualized return / |max drawdown|."""
    if equity is None or equity.empty or returns is None or returns.empty:
        return 0.0
    e = equity.dropna()
    if len(e) < 2:
        return 0.0
    total_return = (e.iloc[-1] / e.iloc[0]) - 1.0
    n_bars = len(e)
    if n_bars == 0:
        return 0.0
    # Annualized return: (1 + total)^(periods/n_bars) - 1
    if total_return <= -1.0:
        return 0.0
    ann_return = (1.0 + total_return) ** (periods / n_bars) - 1.0
    mdd = max_drawdown(equity)
    if mdd == 0:
        return 0.0
    return float(ann_return / abs(mdd))


def win_rate(trades: pd.DataFrame) -> float:
    """Fraction of profitable trades (0..1).

    Expects a `pnl` column. Returns 0.0 if no trades.
    """
    if trades is None or trades.empty or "pnl" not in trades.columns:
        return 0.0
    pnl = trades["pnl"].dropna()
    if len(pnl) == 0:
        return 0.0
    wins = (pnl > 0).sum()
    return float(wins / len(pnl))


def profit_factor(trades: pd.DataFrame) -> float:
    """Gross profit / gross loss.

    Returns float('inf') if there are no losses, 0.0 if no profits.
    """
    if trades is None or trades.empty or "pnl" not in trades.columns:
        return 0.0
    pnl = trades["pnl"].dropna()
    if len(pnl) == 0:
        return 0.0
    gross_profit = pnl[pnl > 0].sum()
    gross_loss = abs(pnl[pnl < 0].sum())
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0
    return float(gross_profit / gross_loss)


def expectancy(trades: pd.DataFrame) -> float:
    """Expected $ PnL per trade.

    = win_rate * avg_win - loss_rate * avg_loss
    (Equivalently: mean of pnl column, but spelled out for clarity.)
    """
    if trades is None or trades.empty or "pnl" not in trades.columns:
        return 0.0
    pnl = trades["pnl"].dropna()
    if len(pnl) == 0:
        return 0.0
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    wr = len(wins) / len(pnl) if len(pnl) > 0 else 0.0
    lr = len(losses) / len(pnl) if len(pnl) > 0 else 0.0
    avg_win = wins.mean() if not wins.empty else 0.0
    avg_loss = abs(losses.mean()) if not losses.empty else 0.0
    return float(wr * avg_win - lr * avg_loss)


# --------------------------------------------------------------------
# Aggregate
# --------------------------------------------------------------------
def compute_all(
    equity: pd.Series,
    trades: pd.DataFrame,
    risk_free: float = 0.0,
    periods: int = 252,
) -> dict:
    """Compute the full metrics dictionary for a backtest run.

    Returns a flat dict with all metrics + a few useful extras.
    """
    # Per-bar returns from equity curve
    if equity is not None and not equity.empty and len(equity) >= 2:
        returns = equity.pct_change().dropna()
    else:
        returns = pd.Series(dtype=float)

    metrics = {
        "total_trades": int(len(trades)) if trades is not None else 0,
        "win_rate": round(win_rate(trades), 4),
        "profit_factor": round(profit_factor(trades), 4) if profit_factor(trades) != float("inf") else float("inf"),
        "sharpe_ratio": round(sharpe_ratio(returns, risk_free, periods), 4),
        "sortino_ratio": round(sortino_ratio(returns, risk_free, periods), 4),
        "calmar_ratio": round(calmar_ratio(returns, equity, periods), 4),
        "max_drawdown": round(max_drawdown(equity), 4),
        "expectancy": round(expectancy(trades), 4),
        "total_return": round(float((equity.iloc[-1] / equity.iloc[0]) - 1.0), 4)
                        if equity is not None and not equity.empty and len(equity) >= 2 and equity.iloc[0] != 0
                        else 0.0,
        "final_equity": float(equity.iloc[-1]) if equity is not None and not equity.empty else 0.0,
    }
    return metrics


__all__ = [
    "sharpe_ratio",
    "sortino_ratio",
    "max_drawdown",
    "calmar_ratio",
    "win_rate",
    "profit_factor",
    "expectancy",
    "compute_all",
]
