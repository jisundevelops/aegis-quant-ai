"""
risk.position_sizing — Position sizing algorithms.

Kelly criterion, fixed-fractional, volatility-targeting, and risk-parity.
Phase 7 implements the concrete formulas.
"""
from __future__ import annotations

from typing import Literal

SizingMethod = Literal["kelly", "fixed_fractional", "vol_target", "risk_parity"]


def kelly_fraction(win_prob: float, win_loss_ratio: float) -> float:
    """Full Kelly fraction. Phase 7."""
    raise NotImplementedError


def fixed_fractional(capital: float, risk_pct: float, stop_distance: float) -> float:
    """Fixed-fractional sizing. Phase 7."""
    raise NotImplementedError


def vol_target_size(capital: float, target_vol: float, asset_vol: float) -> float:
    """Volatility-targeted sizing. Phase 7."""
    raise NotImplementedError


def size_position(
    method: SizingMethod,
    capital: float,
    conviction: float,
    **kwargs,
) -> float:
    """Dispatch to the selected sizing method. Phase 7."""
    raise NotImplementedError
