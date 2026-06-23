"""
agents.macro_agent — Top-down macro regime agent.

Reads DXY (U.S. Dollar Index) and US10Y (^TNX) direction from the Phase 4
feature DataFrame and produces a macro bias for crypto / risk assets.

Rule-based logic (per Phase 5 spec):
  - DXY up      -> crypto bearish (strong dollar pressures risk assets)
  - DXY down    -> crypto bullish (weak dollar supports risk assets)
  - US10Y up    -> crypto bearish (rising yields discount long-duration/risk)
  - US10Y down  -> crypto bullish (falling yields support risk assets)

Both signals are weighted equally. If both agree, confidence is high;
if they disagree, bias is Neutral.

This file replaces the Phase 1 stub. The class name `MacroAgent` and
`name = "macro"` are preserved so Phase 1 imports + tests still pass.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from agents.base_agent import AgentSignal, BaseAgent


class MacroAgent(BaseAgent):
    """Top-down macro agent (DXY + US10Y rule-based)."""

    name = "macro"
    description = "Macro regime agent (DXY + US10Y direction, rule-based)."

    # Symbols used by the Phase 3 Yahoo connector (for reference)
    DXY_SYMBOL = "DX-Y.NYB"
    US10Y_SYMBOL = "^TNX"

    # How many bars to use when computing "direction"
    DEFAULT_LOOKBACK = 20

    def __init__(self, lookback: int | None = None) -> None:
        self.lookback = lookback or self.DEFAULT_LOOKBACK

    async def analyze(
        self,
        symbol: str,
        features_df: pd.DataFrame | None = None,
        dxy_df: pd.DataFrame | None = None,
        us10y_df: pd.DataFrame | None = None,
        **kwargs: Any,
    ) -> AgentSignal:
        """Analyze macro bias from DXY + US10Y.

        Parameters
        ----------
        symbol       : target ticker (e.g. 'BTCUSDT') — bias is for this asset
        features_df  : optional combined feature frame (ignored unless it
                       contains dxy_slope / us10y_slope columns, in which case
                       those are used directly)
        dxy_df       : optional OHLCV frame for DX-Y.NYB (used if features_df
                       doesn't carry pre-computed slopes)
        us10y_df     : optional OHLCV frame for ^TNX
        """
        # Prefer pre-computed slopes from features_df if present
        if features_df is not None and not features_df.empty:
            if "dxy_slope" in features_df.columns and "us10y_slope" in features_df.columns:
                last = features_df.iloc[-1]
                dxy_slope = last.get("dxy_slope")
                us10y_slope = last.get("us10y_slope")
                return self._score(symbol, dxy_slope, us10y_slope)

        # Otherwise compute slopes from the provided DXY / US10Y frames
        dxy_slope = self._compute_slope(dxy_df) if dxy_df is not None else None
        us10y_slope = self._compute_slope(us10y_df) if us10y_df is not None else None
        return self._score(symbol, dxy_slope, us10y_slope)

    # ------------------------------------------------------------------
    def _compute_slope(self, df: pd.DataFrame) -> float | None:
        """Linear-regression slope of `close` over the last `lookback` bars."""
        if df is None or df.empty or "close" not in df.columns:
            return None
        recent = df["close"].dropna().iloc[-self.lookback:]
        if len(recent) < 5:
            return None
        # Normalised slope: (end - start) / start
        start = float(recent.iloc[0])
        end = float(recent.iloc[-1])
        if start == 0:
            return None
        return (end - start) / start

    def _score(
        self,
        symbol: str,
        dxy_slope: float | None,
        us10y_slope: float | None,
    ) -> AgentSignal:
        reasons: list[str] = []
        evidence: dict[str, Any] = {}
        score = 50.0

        # ----- DXY -----
        if dxy_slope is None or pd.isna(dxy_slope):
            reasons.append("DXY slope unavailable")
            evidence["dxy_slope"] = None
        else:
            evidence["dxy_slope"] = float(dxy_slope)
            if dxy_slope > 0.001:  # +0.1% over window
                score -= 15
                reasons.append(f"DXY up {dxy_slope*100:.2f}% (bearish for crypto)")
            elif dxy_slope < -0.001:
                score += 15
                reasons.append(f"DXY down {dxy_slope*100:.2f}% (bullish for crypto)")
            else:
                reasons.append(f"DXY flat ({dxy_slope*100:.2f}%)")

        # ----- US10Y -----
        if us10y_slope is None or pd.isna(us10y_slope):
            reasons.append("US10Y slope unavailable")
            evidence["us10y_slope"] = None
        else:
            evidence["us10y_slope"] = float(us10y_slope)
            if us10y_slope > 0.005:  # +0.5% over window (yields are ~4%, so 0.5% is meaningful)
                score -= 15
                reasons.append(f"US10Y up {us10y_slope*100:.2f}% (bearish for risk)")
            elif us10y_slope < -0.005:
                score += 15
                reasons.append(f"US10Y down {us10y_slope*100:.2f}% (bullish for risk)")
            else:
                reasons.append(f"US10Y flat ({us10y_slope*100:.2f}%)")

        score = float(np.clip(score, 0.0, 100.0))
        if score >= 65:
            bias = "Bullish"
        elif score <= 35:
            bias = "Bearish"
        else:
            bias = "Neutral"

        confidence = float(np.clip(abs(score - 50.0) * 2.0, 0.0, 100.0))

        return AgentSignal(
            agent=self.name,
            symbol=symbol,
            bias=bias,
            confidence=confidence,
            reasoning="; ".join(reasons),
            evidence=evidence,
        )


__all__ = ["MacroAgent"]
