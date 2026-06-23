"""
features.smc — Smart Money Concepts (pure pandas/numpy, no fake libs).

Implements:
  - Swing pivot detection (the backbone of all SMC)
  - BOS  (Break of Structure)         — trend continuation
  - CHOCH (Change of Character)       — trend reversal
  - FVG (Fair Value Gap)              — 3-bar imbalance
  - Order Block                       — last opposite candle before strong move
  - Equal Highs / Equal Lows          — liquidity pools
  - Liquidity Sweep                   — wick takes prior pivot then reverses

Every feature returns a column on the same OHLCV DataFrame. Where a
pattern is detected at bar `i`, the column carries a directional label
('bull', 'bear', or NaN). Companion numeric columns carry the price
level of the detected pattern (e.g. `bos_level`).

All implementations are O(N) or O(N*K) with small K (pivot lookback).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from features.base import BaseFeature


# --------------------------------------------------------------------
# Pivot detection (used by BOS, CHOCH, Equal H/L, Liquidity Sweep)
# --------------------------------------------------------------------
def find_pivots(
    df: pd.DataFrame,
    lookback: int = 5,
) -> tuple[pd.Series, pd.Series]:
    """Detect swing highs and swing lows.

    A bar is a swing high if its `high` is the strictly-greatest high
    over the window [i-lookback, i+lookback]. Symmetric for swing lows.

    Returns
    -------
    (swing_high, swing_low) : two boolean Series indexed like df
    """
    high = df["high"]
    low = df["low"]
    n = len(df)
    sh = np.zeros(n, dtype=bool)
    sl = np.zeros(n, dtype=bool)

    high_vals = high.values
    low_vals = low.values

    for i in range(lookback, n - lookback):
        window_high = high_vals[i - lookback : i + lookback + 1]
        window_low = low_vals[i - lookback : i + lookback + 1]
        # Strictly greater than all other bars in window
        if high_vals[i] == window_high.max() and np.sum(window_high == high_vals[i]) == 1:
            sh[i] = True
        if low_vals[i] == window_low.min() and np.sum(window_low == low_vals[i]) == 1:
            sl[i] = True

    return (
        pd.Series(sh, index=df.index, name="swing_high"),
        pd.Series(sl, index=df.index, name="swing_low"),
    )


# --------------------------------------------------------------------
# Main feature class
# --------------------------------------------------------------------
class SmartMoneyFeatures(BaseFeature):
    """Smart Money Concepts feature pack."""

    name = "smc"

    def __init__(self, pivot_lookback: int = 5, equal_tol: float = 0.001) -> None:
        """
        Parameters
        ----------
        pivot_lookback : bars on each side of a pivot
        equal_tol      : tolerance for equal highs/lows (fraction of price)
        """
        self.pivot_lookback = pivot_lookback
        self.equal_tol = equal_tol

    # ------------------------------------------------------------------
    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return df copy with all SMC columns appended."""
        if df is None or df.empty:
            return df.copy() if df is not None else df

        required = {"high", "low", "close"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"SmartMoneyFeatures requires columns: {missing}")

        out = df.copy()
        for col in ("open", "high", "low", "close", "volume"):
            if col in out.columns:
                out[col] = pd.to_numeric(out[col], errors="coerce")

        # Initialise SMC columns.
        # Numeric columns start as float NaN; categorical columns must
        # be object dtype so we can later assign string labels like 'bull'.
        out["swing_high"] = False
        out["swing_low"] = False
        out["bos"] = pd.Series([np.nan] * len(out), index=out.index, dtype="object")
        out["bos_level"] = np.nan
        out["choch"] = pd.Series([np.nan] * len(out), index=out.index, dtype="object")
        out["choch_level"] = np.nan
        out["fvg"] = pd.Series([np.nan] * len(out), index=out.index, dtype="object")
        out["fvg_top"] = np.nan
        out["fvg_bottom"] = np.nan
        out["order_block"] = pd.Series([np.nan] * len(out), index=out.index, dtype="object")
        out["ob_high"] = np.nan
        out["ob_low"] = np.nan
        out["equal_highs"] = False
        out["equal_lows"] = False
        out["liquidity_sweep"] = pd.Series([np.nan] * len(out), index=out.index, dtype="object")

        # Pivots
        sh, sl = find_pivots(out, lookback=self.pivot_lookback)
        out["swing_high"] = sh
        out["swing_low"] = sl

        # BOS + CHOCH
        self._detect_bos_choch(out)

        # FVG
        self._detect_fvg(out)

        # Order Blocks
        self._detect_order_blocks(out)

        # Equal Highs / Lows
        self._detect_equal_extremes(out)

        # Liquidity Sweep
        self._detect_liquidity_sweeps(out)

        return out

    # ------------------------------------------------------------------
    # BOS / CHOCH
    # ------------------------------------------------------------------
    def _detect_bos_choch(self, df: pd.DataFrame) -> None:
        """Detect Break of Structure and Change of Character.

        - BOS:   close breaks the last same-direction swing
                 (e.g. in an uptrend, close > prior swing high)
        - CHOCH: close breaks the last opposite-direction swing
                 (e.g. in an uptrend, close < prior swing low)
        """
        highs = df["high"].values
        lows = df["low"].values
        closes = df["close"].values
        sh = df["swing_high"].values
        sl = df["swing_low"].values
        n = len(df)

        # Track last confirmed swing high/low + their levels + the trend
        last_sh_idx: int | None = None
        last_sh_level: float | None = None
        last_sl_idx: int | None = None
        last_sl_level: float | None = None
        trend: str = "neutral"  # 'up' | 'down' | 'neutral'

        for i in range(n):
            # Register newly-visible pivots (a pivot at i becomes visible
            # at i + pivot_lookback, but we use it once we walk past it).
            # We use the boolean series directly: if sh[i] is True, register.
            if sh[i]:
                last_sh_idx = i
                last_sh_level = highs[i]
            if sl[i]:
                last_sl_idx = i
                last_sl_level = lows[i]

            # Update trend based on the order of last swings
            if last_sh_idx is not None and last_sl_idx is not None:
                if last_sh_idx > last_sl_idx:
                    trend = "up"
                else:
                    trend = "down"

            # BOS / CHOCH checks
            if trend == "up" and last_sh_level is not None:
                # Close above last swing high in an uptrend = BOS up
                if closes[i] > last_sh_level:
                    df.iloc[i, df.columns.get_loc("bos")] = "bull"
                    df.iloc[i, df.columns.get_loc("bos_level")] = last_sh_level
                    # Shift the structural high upward
                    last_sh_level = closes[i]
                # Close below last swing low in an uptrend = CHOCH (reversal)
                if last_sl_level is not None and closes[i] < last_sl_level:
                    df.iloc[i, df.columns.get_loc("choch")] = "bear"
                    df.iloc[i, df.columns.get_loc("choch_level")] = last_sl_level
                    trend = "down"  # trend has flipped

            elif trend == "down" and last_sl_level is not None:
                # Close below last swing low in a downtrend = BOS down
                if closes[i] < last_sl_level:
                    df.iloc[i, df.columns.get_loc("bos")] = "bear"
                    df.iloc[i, df.columns.get_loc("bos_level")] = last_sl_level
                    last_sl_level = closes[i]
                # Close above last swing high in a downtrend = CHOCH (reversal)
                if last_sh_level is not None and closes[i] > last_sh_level:
                    df.iloc[i, df.columns.get_loc("choch")] = "bull"
                    df.iloc[i, df.columns.get_loc("choch_level")] = last_sh_level
                    trend = "up"

    # ------------------------------------------------------------------
    # Fair Value Gap
    # ------------------------------------------------------------------
    def _detect_fvg(self, df: pd.DataFrame) -> None:
        """3-candle imbalance.

        Bullish FVG at i:  high[i-2] < low[i]      (gap up between bar 1 and bar 3)
        Bearish FVG at i:  low[i-2]  > high[i]     (gap down between bar 1 and bar 3)
        """
        high = df["high"].values
        low = df["low"].values
        n = len(df)
        for i in range(2, n):
            # Bullish FVG
            if high[i - 2] < low[i]:
                df.iloc[i, df.columns.get_loc("fvg")] = "bull"
                df.iloc[i, df.columns.get_loc("fvg_bottom")] = high[i - 2]
                df.iloc[i, df.columns.get_loc("fvg_top")] = low[i]
            # Bearish FVG
            elif low[i - 2] > high[i]:
                df.iloc[i, df.columns.get_loc("fvg")] = "bear"
                df.iloc[i, df.columns.get_loc("fvg_top")] = low[i - 2]
                df.iloc[i, df.columns.get_loc("fvg_bottom")] = high[i]

    # ------------------------------------------------------------------
    # Order Blocks
    # ------------------------------------------------------------------
    def _detect_order_blocks(self, df: pd.DataFrame) -> None:
        """Last opposite-color candle before a strong move.

        A 'strong move' is defined as a bar whose body exceeds 1.5x the
        rolling ATR-proxy (mean of recent true ranges). The order block
        is the most recent opposite-color candle within the prior 3 bars.
        """
        open_ = df["open"].values
        close = df["close"].values
        high = df["high"].values
        low = df["low"].values
        n = len(df)

        # Body size + simple volatility proxy (rolling mean of TR)
        body = np.abs(close - open_)
        tr = np.maximum(
            high - low,
            np.maximum(
                np.abs(high - np.roll(close, 1)),
                np.abs(low - np.roll(close, 1)),
            ),
        )
        tr[0] = high[0] - low[0]
        vol_proxy = pd.Series(tr).rolling(14, min_periods=1).mean().values

        for i in range(1, n):
            if vol_proxy[i] == 0 or np.isnan(vol_proxy[i]):
                continue
            is_strong_bull = close[i] > open_[i] and body[i] > 1.5 * vol_proxy[i]
            is_strong_bear = close[i] < open_[i] and body[i] > 1.5 * vol_proxy[i]
            if not (is_strong_bull or is_strong_bear):
                continue

            # Look back up to 3 bars for the last opposite-color candle
            window_start = max(0, i - 3)
            for j in range(i - 1, window_start - 1, -1):
                if j < 0:
                    break
                candle_j_bull = close[j] > open_[j]
                candle_j_bear = close[j] < open_[j]
                if is_strong_bull and candle_j_bear:
                    df.iloc[i, df.columns.get_loc("order_block")] = "bull"
                    df.iloc[i, df.columns.get_loc("ob_high")] = high[j]
                    df.iloc[i, df.columns.get_loc("ob_low")] = low[j]
                    break
                if is_strong_bear and candle_j_bull:
                    df.iloc[i, df.columns.get_loc("order_block")] = "bear"
                    df.iloc[i, df.columns.get_loc("ob_high")] = high[j]
                    df.iloc[i, df.columns.get_loc("ob_low")] = low[j]
                    break

    # ------------------------------------------------------------------
    # Equal Highs / Equal Lows
    # ------------------------------------------------------------------
    def _detect_equal_extremes(self, df: pd.DataFrame) -> None:
        """Flag bars where two or more swing pivots sit within `equal_tol`.

        We compare the most recent swing high/low against the previous
        swing of the same kind. If the absolute difference is within
        `equal_tol * price`, we flag the bar where the second pivot was
        registered.
        """
        sh_idx = np.where(df["swing_high"].values)[0]
        sl_idx = np.where(df["swing_low"].values)[0]
        high = df["high"].values
        low = df["low"].values

        # Compare consecutive swing highs
        for k in range(1, len(sh_idx)):
            prev_level = high[sh_idx[k - 1]]
            curr_level = high[sh_idx[k]]
            if prev_level > 0 and abs(curr_level - prev_level) / prev_level <= self.equal_tol:
                df.iloc[sh_idx[k], df.columns.get_loc("equal_highs")] = True

        # Compare consecutive swing lows
        for k in range(1, len(sl_idx)):
            prev_level = low[sl_idx[k - 1]]
            curr_level = low[sl_idx[k]]
            if prev_level > 0 and abs(curr_level - prev_level) / prev_level <= self.equal_tol:
                df.iloc[sl_idx[k], df.columns.get_loc("equal_lows")] = True

    # ------------------------------------------------------------------
    # Liquidity Sweep
    # ------------------------------------------------------------------
    def _detect_liquidity_sweeps(self, df: pd.DataFrame) -> None:
        """Detect liquidity sweeps (stop hunts).

        A bullish sweep at bar i:
          - the bar's low pierced below the most recent prior swing low
            (wick_down < last_swing_low)
          - but the close recovered back above it (close > last_swing_low)

        Symmetric for bearish sweeps against the most recent prior swing high.
        """
        high = df["high"].values
        low = df["low"].values
        close = df["close"].values
        sh = df["swing_high"].values
        sl = df["swing_low"].values
        n = len(df)

        last_sl_level: float | None = None
        last_sh_level: float | None = None

        for i in range(n):
            # Update tracked swing levels *after* the test (so we use
            # only PRIOR pivots, not the current bar's own pivot).
            # Bullish sweep: low pierced prior swing low but close recovered
            if last_sl_level is not None:
                if low[i] < last_sl_level and close[i] > last_sl_level:
                    df.iloc[i, df.columns.get_loc("liquidity_sweep")] = "bull"
            # Bearish sweep: high pierced prior swing high but close recovered
            if last_sh_level is not None:
                if high[i] > last_sh_level and close[i] < last_sh_level:
                    df.iloc[i, df.columns.get_loc("liquidity_sweep")] = "bear"
            # Now register the current bar's pivots for future bars
            if sl[i]:
                last_sl_level = low[i]
            if sh[i]:
                last_sh_level = high[i]


__all__ = ["SmartMoneyFeatures", "find_pivots"]
