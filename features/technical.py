"""
features.technical — Technical indicator features (pandas-ta backed).

Computes institutional-grade technical indicators from an OHLCV DataFrame:
  - EMA20, EMA50, EMA200  (trend)
  - RSI(14)               (momentum)
  - MACD(12, 26, 9)       (trend/momentum)
  - ATR(14)               (volatility)
  - VWAP                  (intraday fair value)
  - Volume MA(20)         (liquidity baseline)

All indicators are computed via the `pandas-ta` library. The result is a
new DataFrame with the original OHLCV columns plus one column per
indicator (named using the canonical Aegis schema).

Input contract:
  - DataFrame indexed by tz-aware timestamp
  - Required columns: open, high, low, close, volume

Output contract:
  - Same index, same OHLCV columns
  - Added columns: ema_20, ema_50, ema_200, rsi_14,
                   macd_line, macd_signal, macd_hist,
                   atr_14, vwap, volume_ma_20
  - NaN rows are NOT dropped here — the combiner is responsible for
    validating final output. Dropping here would lose the latest bar.
"""
from __future__ import annotations

import pandas as pd
import pandas_ta as ta  # type: ignore

from features.base import BaseFeature


class TechnicalFeatures(BaseFeature):
    """All standard technical indicators in one compute() pass."""

    name = "technical"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return a copy of df with technical indicator columns appended.

        Parameters
        ----------
        df : DataFrame with columns open, high, low, close, volume
             (tz-aware timestamp index recommended for VWAP)

        Returns
        -------
        DataFrame with new columns:
            ema_20, ema_50, ema_200, rsi_14,
            macd_line, macd_signal, macd_hist,
            atr_14, vwap, volume_ma_20
        """
        if df is None or df.empty:
            return df.copy() if df is not None else df

        required = {"open", "high", "low", "close", "volume"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"TechnicalFeatures requires columns: {missing}")

        out = df.copy()
        # Ensure float dtype for indicator inputs
        for col in ("open", "high", "low", "close", "volume"):
            out[col] = pd.to_numeric(out[col], errors="coerce")

        # ---------- EMAs ----------
        out["ema_20"] = ta.ema(out["close"], length=20)
        out["ema_50"] = ta.ema(out["close"], length=50)
        out["ema_200"] = ta.ema(out["close"], length=200)

        # ---------- RSI ----------
        out["rsi_14"] = ta.rsi(out["close"], length=14)

        # ---------- MACD ----------
        macd_df = ta.macd(out["close"], fast=12, slow=26, signal=9)
        if macd_df is not None and not macd_df.empty:
            # Columns: MACD_12_26_9, MACDh_12_26_9, MACDs_12_26_9
            out["macd_line"] = macd_df.iloc[:, 0]
            out["macd_hist"] = macd_df.iloc[:, 1]
            out["macd_signal"] = macd_df.iloc[:, 2]
        else:
            # Fallback: manual MACD
            ema_fast = out["close"].ewm(span=12, adjust=False).mean()
            ema_slow = out["close"].ewm(span=26, adjust=False).mean()
            macd_line = ema_fast - ema_slow
            out["macd_line"] = macd_line
            out["macd_signal"] = macd_line.ewm(span=9, adjust=False).mean()
            out["macd_hist"] = macd_line - out["macd_signal"]

        # ---------- ATR ----------
        out["atr_14"] = ta.atr(out["high"], out["low"], out["close"], length=14)

        # ---------- VWAP ----------
        # pandas-ta's vwap requires a datetime index. If the caller passed
        # a non-datetime index, fall back to rolling VWAP over 20 bars.
        out["vwap"] = self._safe_vwap(out)

        # ---------- Volume MA ----------
        out["volume_ma_20"] = out["volume"].rolling(window=20, min_periods=1).mean()

        return out

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _safe_vwap(df: pd.DataFrame) -> pd.Series:
        """Compute VWAP — uses pandas-ta if index is datetime, else rolling fallback."""
        typical = (df["high"] + df["low"] + df["close"]) / 3.0
        try:
            vwap = ta.vwap(df["high"], df["low"], df["close"], df["volume"])
            if vwap is not None and not vwap.isna().all():
                return vwap
        except Exception:  # noqa: BLE001
            pass
        # Rolling fallback: 20-bar anchored-style VWAP
        return (typical * df["volume"]).rolling(20, min_periods=1).sum() / \
               df["volume"].rolling(20, min_periods=1).sum()


__all__ = ["TechnicalFeatures"]
