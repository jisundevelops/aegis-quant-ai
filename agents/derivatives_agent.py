"""
agents.derivatives_agent — Derivatives positioning agent.

Reads the Phase 4 derivatives feature columns and produces a positioning
bias based on:
  - Open Interest (rising/falling)
  - Funding Rate (positive = longs pay shorts = crowded long)
  - Long/Short Ratio (above/below 1.0)
  - CVD slope over recent window (aggressive buying vs selling)

Output: AgentSignal with bias ∈ {Bullish, Bearish, Neutral}, confidence 0..100.

Confidence model:
  - Start at 50.
  - Funding rate > +0.0005 (crowded long)  -> -10  (contrarian bearish)
  - Funding rate < -0.0005 (crowded short) -> +10  (contrarian bullish)
  - L/S ratio > 1.5 (longs crowded)        -> -8
  - L/S ratio < 0.7 (shorts crowded)       -> +8
  - CVD slope up (last 20 bars)            -> +15
  - CVD slope down (last 20 bars)          -> -15
  - OI rising + price up = trend strength  -> +5  (only when both agree)
  - OI falling + price up = weak hand      -> -5
  - Clamp to [0, 100].
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from agents.base_agent import AgentSignal, BaseAgent


class DerivativesAgent(BaseAgent):
    name = "derivatives"
    description = "Derivatives positioning agent (OI/Funding/L-S/CVD)."

    # Funding rate thresholds (Binance perpetuals typically ±0.01% per 8h)
    FUNDING_CROWDED_LONG = 0.0005    # >+0.05% = longs paying hard
    FUNDING_CROWDED_SHORT = -0.0005  # <-0.05% = shorts paying hard
    LS_CROWDED_LONG = 1.5
    LS_CROWDED_SHORT = 0.7

    def __init__(self, cvd_window: int = 20) -> None:
        self.cvd_window = cvd_window

    async def analyze(
        self,
        symbol: str,
        features_df: pd.DataFrame | None = None,
        **kwargs: Any,
    ) -> AgentSignal:
        if features_df is None or features_df.empty:
            return self._neutral(symbol, "No feature data provided.")

        required = {"open_interest", "funding_rate", "long_short_ratio", "cvd"}
        missing = required - set(features_df.columns)
        if missing:
            return self._neutral(
                symbol, f"Missing required derivatives columns: {missing}"
            )

        last = features_df.iloc[-1]
        score = 50.0
        reasons: list[str] = []
        evidence: dict[str, Any] = {}

        # ----- Funding rate -----
        funding = last["funding_rate"]
        evidence["funding_rate"] = float(funding) if not pd.isna(funding) else None
        if not pd.isna(funding):
            if funding > self.FUNDING_CROWDED_LONG:
                score -= 10
                reasons.append(f"Funding {funding*100:.4f}% (longs crowded, contrarian bearish)")
            elif funding < self.FUNDING_CROWDED_SHORT:
                score += 10
                reasons.append(f"Funding {funding*100:.4f}% (shorts crowded, contrarian bullish)")
            else:
                reasons.append(f"Funding {funding*100:.4f}% (neutral)")
        else:
            reasons.append("Funding rate NaN")

        # ----- Long/Short ratio -----
        ls = last["long_short_ratio"]
        evidence["long_short_ratio"] = float(ls) if not pd.isna(ls) else None
        if not pd.isna(ls):
            if ls > self.LS_CROWDED_LONG:
                score -= 8
                reasons.append(f"L/S {ls:.2f} (longs crowded)")
            elif ls < self.LS_CROWDED_SHORT:
                score += 8
                reasons.append(f"L/S {ls:.2f} (shorts crowded)")
            else:
                reasons.append(f"L/S {ls:.2f} (balanced)")
        else:
            reasons.append("L/S ratio NaN")

        # ----- CVD slope -----
        cvd = features_df["cvd"].dropna()
        evidence["cvd_latest"] = float(cvd.iloc[-1]) if not cvd.empty else None
        if len(cvd) >= self.cvd_window:
            recent = cvd.iloc[-self.cvd_window:]
            slope = recent.iloc[-1] - recent.iloc[0]
            evidence["cvd_slope"] = float(slope)
            if slope > 0:
                score += 15
                reasons.append(f"CVD rising over {self.cvd_window} bars (+{slope:.2f}, aggressive buying)")
            elif slope < 0:
                score -= 15
                reasons.append(f"CVD falling over {self.cvd_window} bars ({slope:.2f}, aggressive selling)")
            else:
                reasons.append("CVD flat")
        else:
            reasons.append(f"CVD series too short for slope (have {len(cvd)}, need {self.cvd_window})")

        # ----- OI + price agreement -----
        oi = last["open_interest"]
        close = last["close"] if "close" in features_df.columns else None
        evidence["open_interest"] = float(oi) if not pd.isna(oi) else None
        if not pd.isna(oi) and len(features_df) >= 2:
            oi_prev = features_df["open_interest"].iloc[-2]
            if not pd.isna(oi_prev) and oi_prev > 0:
                oi_delta_pct = (oi - oi_prev) / oi_prev
                evidence["oi_delta_pct"] = float(oi_delta_pct)
                if close is not None and not pd.isna(close):
                    close_prev = features_df["close"].iloc[-2] if "close" in features_df.columns else None
                    if close_prev is not None and not pd.isna(close_prev):
                        price_up = close > close_prev
                        if oi_delta_pct > 0.01 and price_up:
                            score += 5
                            reasons.append("OI rising + price up (trend strength)")
                        elif oi_delta_pct < -0.01 and price_up:
                            score -= 5
                            reasons.append("OI falling + price up (weak-hand short covering)")

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

    def _neutral(self, symbol: str, reason: str) -> AgentSignal:
        return AgentSignal(
            agent=self.name,
            symbol=symbol,
            bias="Neutral",
            confidence=0.0,
            reasoning=reason,
            evidence={},
        )


__all__ = ["DerivativesAgent"]
