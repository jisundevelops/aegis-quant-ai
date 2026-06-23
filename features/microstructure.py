"""
features.microstructure — Microstructure features.

Order-flow imbalance, volume-weighted price impact, bid-ask spread
statistics, and trade intensity. Phase 3 implements the concrete
formulas against real L1/L2 data from the connectors.
"""
from __future__ import annotations

import pandas as pd

from features.base import BaseFeature


class VolumeWeightedPriceImpact(BaseFeature):
    """Kyle's lambda-style price impact estimate."""

    name = "vwap_impact"

    def __init__(self, window: int = 20) -> None:
        self.window = window

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out[f"price_impact_{self.window}"] = float("nan")  # Phase 3
        return out


class OrderFlowImbalance(BaseFeature):
    """Signed volume imbalance proxy."""

    name = "ofi"

    def __init__(self, window: int = 20) -> None:
        self.window = window

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out[f"ofi_{self.window}"] = float("nan")  # Phase 3
        return out


class TradeIntensity(BaseFeature):
    """Trades-per-unit-time intensity."""

    name = "trade_intensity"

    def __init__(self, window: int = 20) -> None:
        self.window = window

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out[f"trade_intensity_{self.window}"] = float("nan")  # Phase 3
        return out
