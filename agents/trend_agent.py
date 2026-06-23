"""
agents.trend_agent — Trend-following agent.

Reads the Phase 4 feature DataFrame and produces a trend bias based on:
  1. EMA alignment (EMA20 vs EMA50 vs EMA200)
  2. MACD (line vs signal + histogram sign)
  3. RSI(14) (overbought/oversold + centerline bias)

Output: AgentSignal with bias ∈ {Bullish, Bearish, Neutral}, confidence 0..100,
and a human-readable reasoning string citing the latest values.

Confidence model:
  - Start at 50 (Neutral).
  - EMA alignment (20>50>200 OR 20<50<200)  -> ±20
  - MACD line above/below signal              -> ±15
  - MACD histogram sign                       -> ±5
  - RSI above/below 50                        -> ±10
  - Clamp to [0, 100].
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from agents.base_agent import AgentSignal, BaseAgent


class TrendAgent(BaseAgent):
    name = "trend"
    description = "Trend-following agent (EMA alignment + MACD + RSI)."

    async def analyze(
        self,
        symbol: str,
        features_df: pd.DataFrame | None = None,
        **kwargs: Any,
    ) -> AgentSignal:
        """Analyze trend from the feature DataFrame.

        Parameters
        ----------
        symbol       : ticker
        features_df  : Phase 4 combined feature DataFrame (must contain
                       ema_20, ema_50, ema_200, rsi_14, macd_line,
                       macd_signal, macd_hist)
        """
        if features_df is None or features_df.empty:
            return self._neutral(symbol, "No feature data provided.")

        required = {"ema_20", "ema_50", "ema_200", "rsi_14",
                    "macd_line", "macd_signal", "macd_hist"}
        missing = required - set(features_df.columns)
        if missing:
            return self._neutral(
                symbol, f"Missing required feature columns: {missing}"
            )

        last = features_df.iloc[-1]
        # Drop NaNs — if any required value is NaN, fall back to neutral.
        vals = {
            "ema_20": last["ema_20"], "ema_50": last["ema_50"],
            "ema_200": last["ema_200"], "rsi_14": last["rsi_14"],
            "macd_line": last["macd_line"], "macd_signal": last["macd_signal"],
            "macd_hist": last["macd_hist"],
        }
        if any(pd.isna(v) for v in vals.values()):
            return self._neutral(
                symbol, "Latest feature row has NaN values; cannot analyze."
            )

        score = 50.0
        reasons: list[str] = []

        # ----- EMA alignment -----
        e20, e50, e200 = vals["ema_20"], vals["ema_50"], vals["ema_200"]
        if e20 > e50 > e200:
            score += 20
            reasons.append(f"EMA20>{e50:.2f}>EMA50>{e200:.2f}>EMA200 (bullish stack)")
        elif e20 < e50 < e200:
            score -= 20
            reasons.append(f"EMA20<{e50:.2f}<EMA50<{e200:.2f}<EMA200 (bearish stack)")
        else:
            reasons.append("EMAs not aligned (mixed)")

        # ----- MACD -----
        macd_line, macd_sig, macd_hist = (
            vals["macd_line"], vals["macd_signal"], vals["macd_hist"]
        )
        if macd_line > macd_sig:
            score += 15
            reasons.append(f"MACD line ({macd_line:.4f}) > signal ({macd_sig:.4f})")
        elif macd_line < macd_sig:
            score -= 15
            reasons.append(f"MACD line ({macd_line:.4f}) < signal ({macd_sig:.4f})")

        if macd_hist > 0:
            score += 5
            reasons.append(f"MACD histogram positive ({macd_hist:.4f})")
        elif macd_hist < 0:
            score -= 5
            reasons.append(f"MACD histogram negative ({macd_hist:.4f})")

        # ----- RSI -----
        rsi = vals["rsi_14"]
        if rsi > 55:
            score += 10
            reasons.append(f"RSI {rsi:.1f} above 55 (bullish momentum)")
        elif rsi < 45:
            score -= 10
            reasons.append(f"RSI {rsi:.1f} below 45 (bearish momentum)")
        else:
            reasons.append(f"RSI {rsi:.1f} neutral (45-55)")

        # ----- Map score to bias -----
        score = float(np.clip(score, 0.0, 100.0))
        if score >= 65:
            bias = "Bullish"
        elif score <= 35:
            bias = "Bearish"
        else:
            bias = "Neutral"

        # Move confidence away from 50 based on |score - 50|
        confidence = abs(score - 50.0) * 2.0  # 0..100
        confidence = float(np.clip(confidence, 0.0, 100.0))

        return AgentSignal(
            agent=self.name,
            symbol=symbol,
            bias=bias,
            confidence=confidence,
            reasoning="; ".join(reasons),
            evidence={**{k: float(v) for k, v in vals.items()}, "score": score},
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


__all__ = ["TrendAgent"]
