"""
agents.smc_agent — Smart Money Concepts agent.

Reads the Phase 4 SMC feature columns and produces an institutional bias
based on:
  - BOS direction (bull/bear) over the last N bars
  - CHOCH direction (reversal signal)
  - FVG presence + direction (imbalance)
  - Order Block presence + direction
  - Liquidity sweep direction (bull/bear)

Output: AgentSignal with bias ∈ {Bullish, Bearish, Neutral}, confidence 0..100.

Confidence model:
  - Start at 50.
  - Each bullish BOS in window  -> +8  (cap +20)
  - Each bearish BOS in window  -> -8  (cap -20)
  - Latest CHOCH bullish        -> +15
  - Latest CHOCH bearish        -> -15
  - Latest FVG bullish          -> +5
  - Latest FVG bearish          -> -5
  - Latest Order Block bullish  -> +5
  - Latest Order Block bearish  -> -5
  - Latest liquidity sweep bull -> +10 (longs trapped -> reversal up)
  - Latest liquidity sweep bear -> -10
  - Clamp to [0, 100].
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from agents.base_agent import AgentSignal, BaseAgent


class SMCAgent(BaseAgent):
    name = "smc"
    description = "Smart Money Concepts agent (BOS/CHOCH/FVG/OB/Liquidity)."

    def __init__(self, lookback: int = 50) -> None:
        """lookback: number of recent bars to scan for BOS frequency."""
        self.lookback = lookback

    async def analyze(
        self,
        symbol: str,
        features_df: pd.DataFrame | None = None,
        **kwargs: Any,
    ) -> AgentSignal:
        if features_df is None or features_df.empty:
            return self._neutral(symbol, "No feature data provided.")

        required = {"bos", "choch", "fvg", "order_block", "liquidity_sweep"}
        missing = required - set(features_df.columns)
        if missing:
            return self._neutral(
                symbol, f"Missing required SMC columns: {missing}"
            )

        # Use only the last `lookback` bars.
        window = features_df.iloc[-self.lookback :] if len(features_df) >= self.lookback else features_df
        if window.empty:
            return self._neutral(symbol, "Empty feature window.")

        score = 50.0
        reasons: list[str] = []

        # ----- BOS frequency -----
        bull_bos = (window["bos"] == "bull").sum()
        bear_bos = (window["bos"] == "bear").sum()
        score += min(int(bull_bos) * 8, 20)
        score -= min(int(bear_bos) * 8, 20)
        reasons.append(f"BOS in window: {bull_bos} bull, {bear_bos} bear")

        # ----- Latest CHOCH -----
        last_choch = self._last_label(window["choch"])
        if last_choch == "bull":
            score += 15
            reasons.append("Latest CHOCH bullish (potential reversal up)")
        elif last_choch == "bear":
            score -= 15
            reasons.append("Latest CHOCH bearish (potential reversal down)")

        # ----- Latest FVG -----
        last_fvg = self._last_label(window["fvg"])
        if last_fvg == "bull":
            score += 5
            reasons.append("Latest FVG bullish (demand imbalance)")
        elif last_fvg == "bear":
            score -= 5
            reasons.append("Latest FVG bearish (supply imbalance)")

        # ----- Latest Order Block -----
        last_ob = self._last_label(window["order_block"])
        if last_ob == "bull":
            score += 5
            reasons.append("Latest Order Block bullish")
        elif last_ob == "bear":
            score -= 5
            reasons.append("Latest Order Block bearish")

        # ----- Latest Liquidity Sweep -----
        last_sweep = self._last_label(window["liquidity_sweep"])
        if last_sweep == "bull":
            score += 10
            reasons.append("Latest liquidity sweep bullish (stops grabbed below)")
        elif last_sweep == "bear":
            score -= 10
            reasons.append("Latest liquidity sweep bearish (stops grabbed above)")

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
            evidence={
                "bull_bos": int(bull_bos),
                "bear_bos": int(bear_bos),
                "last_choch": last_choch,
                "last_fvg": last_fvg,
                "last_order_block": last_ob,
                "last_liquidity_sweep": last_sweep,
                "score": score,
                "lookback": self.lookback,
            },
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _last_label(series: pd.Series) -> str | None:
        """Return the last non-NaN string label in a Series, or None."""
        cleaned = series.dropna()
        if cleaned.empty:
            return None
        return str(cleaned.iloc[-1])

    def _neutral(self, symbol: str, reason: str) -> AgentSignal:
        return AgentSignal(
            agent=self.name,
            symbol=symbol,
            bias="Neutral",
            confidence=0.0,
            reasoning=reason,
            evidence={},
        )


__all__ = ["SMCAgent"]
