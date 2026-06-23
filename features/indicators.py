"""
features.indicators — Technical indicator features.

Wraps commonly-used indicators (RSI, MACD, EMA, ATR, Bollinger) so they
expose the uniform `BaseFeature` interface. Phase 3 implements the
numerical bodies; this module ships the interface contract today.
"""
from __future__ import annotations

import pandas as pd

from features.base import BaseFeature


class RSI(BaseFeature):
    """Relative Strength Index."""

    name = "rsi"

    def __init__(self, window: int = 14) -> None:
        self.window = window

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out[f"rsi_{self.window}"] = float("nan")  # Phase 3
        return out


class MACD(BaseFeature):
    """Moving Average Convergence Divergence."""

    name = "macd"

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9) -> None:
        self.fast = fast
        self.slow = slow
        self.signal = signal

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out["macd_line"] = float("nan")
        out["macd_signal"] = float("nan")
        out["macd_hist"] = float("nan")  # Phase 3
        return out


class EMA(BaseFeature):
    """Exponential Moving Average."""

    name = "ema"

    def __init__(self, window: int = 20) -> None:
        self.window = window

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out[f"ema_{self.window}"] = float("nan")  # Phase 3
        return out


class ATR(BaseFeature):
    """Average True Range — volatility proxy."""

    name = "atr"

    def __init__(self, window: int = 14) -> None:
        self.window = window

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out[f"atr_{self.window}"] = float("nan")  # Phase 3
        return out


class BollingerBands(BaseFeature):
    """Bollinger Bands (20-period, 2σ)."""

    name = "bollinger"

    def __init__(self, window: int = 20, num_std: float = 2.0) -> None:
        self.window = window
        self.num_std = num_std

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out["bb_mid"] = float("nan")
        out["bb_upper"] = float("nan")
        out["bb_lower"] = float("nan")  # Phase 3
        return out
