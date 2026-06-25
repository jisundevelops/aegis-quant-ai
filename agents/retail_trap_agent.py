"""
agents.retail_trap_agent — Retail trap detector.

Analyzes:
  - Equal Highs / Equal Lows (liquidity pools that retail traders cluster stops around)
  - Recent BOS failures (price broke a structure level then reversed — fakeout)
  - Liquidity sweep pattern frequency
  - Crowd positioning from derivatives (L/S ratio + funding rate)

Estimates four probabilities (each 0..1):
  - stop_hunt_probability       : chance price spikes to grab stops then reverses
  - fake_breakout_probability   : chance a "breakout" fails and reverses
  - short_squeeze_probability   : chance crowded shorts get squeezed up
  - long_squeeze_probability    : chance crowded longs get squeezed down

Output: AgentSignal subclass `TrapAnalysis` with `trap_probabilities` dict.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from pydantic import Field

from agents.base_agent import AgentSignal, BaseAgent


class TrapAnalysis(AgentSignal):
    """Output of the retail trap agent — bias + trap probabilities."""

    trap_probabilities: dict[str, float] = Field(
        default_factory=dict,
        description="stop_hunt / fake_breakout / short_squeeze / long_squeeze probabilities (0..1)",
    )


class RetailTrapAgent(BaseAgent):
    name = "retail_trap"
    description = "Retail trap detector (Equal H/L + BOS failures + crowd positioning)."

    def __init__(self, lookback: int = 50) -> None:
        self.lookback = lookback

    async def analyze(
        self,
        symbol: str,
        features_df: pd.DataFrame | None = None,
        **kwargs: Any,
    ) -> TrapAnalysis:
        if features_df is None or features_df.empty:
            return self._neutral(symbol, "No feature data provided.")

        required = {"equal_highs", "equal_lows", "bos", "liquidity_sweep"}
        missing = required - set(features_df.columns)
        if missing:
            return self._neutral(
                symbol, f"Missing required columns: {missing}"
            )

        window = features_df.iloc[-self.lookback:] if len(features_df) >= self.lookback else features_df

        # ---- Inputs ----
        eq_high_count = int(window["equal_highs"].sum())
        eq_low_count = int(window["equal_lows"].sum())
        bull_bos = int((window["bos"] == "bull").sum())
        bear_bos = int((window["bos"] == "bear").sum())
        sweeps = window["liquidity_sweep"].dropna()
        sweep_count = int(len(sweeps))

        # Crowd positioning (from derivatives if available)
        ls_ratio = float(window["long_short_ratio"].dropna().iloc[-1]) \
                   if "long_short_ratio" in window.columns and not window["long_short_ratio"].dropna().empty \
                   else 1.0
        funding = float(window["funding_rate"].dropna().iloc[-1]) \
                  if "funding_rate" in window.columns and not window["funding_rate"].dropna().empty \
                  else 0.0

        # ---- Probabilities (rule-based, calibrated heuristics) ----
        # Stop hunt probability: higher when more equal highs/lows exist (liquidity pools)
        # plus more prior sweeps (smart money has been raiding stops).
        liquidity_pool_score = min((eq_high_count + eq_low_count) / 5.0, 1.0)
        sweep_freq_score = min(sweep_count / 5.0, 1.0)
        stop_hunt_prob = float(np.clip(0.25 * liquidity_pool_score + 0.35 * sweep_freq_score + 0.1, 0.0, 0.95))

        # Fake breakout probability: ratio of BOS that immediately reversed (CHOCH within 3 bars)
        # Approximated: if there are roughly equal numbers of bull/bear BOS in window, both sides are
        # failing — high fakeout risk.
        bos_total = bull_bos + bear_bos
        if bos_total > 0:
            bos_balance = 1.0 - abs(bull_bos - bear_bos) / max(bos_total, 1)
        else:
            bos_balance = 0.0
        fake_breakout_prob = float(np.clip(0.3 + 0.4 * bos_balance + 0.1 * sweep_freq_score, 0.0, 0.95))

        # Short squeeze probability: high when shorts are crowded (L/S < 0.7) AND funding very negative
        # AND price has just broken up structurally (bull BOS present)
        short_squeeze_prob = 0.0
        if ls_ratio < 0.8 and funding < -0.0003 and bull_bos > 0:
            short_squeeze_prob = float(np.clip(0.45 + 0.25 * (1 - ls_ratio) + 0.1, 0.0, 0.95))
        else:
            short_squeeze_prob = float(np.clip(0.1 + 0.2 * (1 - ls_ratio) if ls_ratio < 1.0 else 0.05, 0.0, 0.5))

        # Long squeeze probability: symmetric — longs crowded (L/S > 1.3) + funding very positive + bear BOS
        long_squeeze_prob = 0.0
        if ls_ratio > 1.3 and funding > 0.0003 and bear_bos > 0:
            long_squeeze_prob = float(np.clip(0.45 + 0.2 * (ls_ratio - 1) + 0.1, 0.0, 0.95))
        else:
            long_squeeze_prob = float(np.clip(0.1 + 0.2 * (ls_ratio - 1) if ls_ratio > 1.0 else 0.05, 0.0, 0.5))

        # ---- Bias: weighted by trap probabilities ----
        # If short squeeze > long squeeze, bias bullish (shorts will be forced to buy)
        # If long squeeze > short squeeze, bias bearish
        score = 50.0
        score += (short_squeeze_prob - long_squeeze_prob) * 40
        # Only apply sweep bonus if there ARE sweeps (guard against empty series)
        if sweep_count > 0 and not sweeps.empty:
            last_sweep = sweeps.iloc[-1]
            if last_sweep == "bull":
                score += 5
            elif last_sweep == "bear":
                score -= 5
        score = float(np.clip(score, 0.0, 100.0))

        if score >= 65:
            bias = "Bullish"
        elif score <= 35:
            bias = "Bearish"
        else:
            bias = "Neutral"

        confidence = float(np.clip(abs(score - 50.0) * 2.0, 0.0, 100.0))

        reasons = [
            f"Equal H/L pools: {eq_high_count}H / {eq_low_count}L",
            f"BOS in window: {bull_bos} bull / {bear_bos} bear (balance={bos_balance:.2f})",
            f"Liquidity sweeps: {sweep_count}",
            f"L/S ratio: {ls_ratio:.2f}, funding: {funding*100:.4f}%",
            f"Stop hunt prob: {stop_hunt_prob:.2f}",
            f"Fake breakout prob: {fake_breakout_prob:.2f}",
            f"Short squeeze prob: {short_squeeze_prob:.2f}",
            f"Long squeeze prob: {long_squeeze_prob:.2f}",
        ]

        return TrapAnalysis(
            agent=self.name,
            symbol=symbol,
            bias=bias,
            confidence=confidence,
            reasoning="; ".join(reasons),
            evidence={
                "equal_highs": eq_high_count,
                "equal_lows": eq_low_count,
                "bull_bos": bull_bos,
                "bear_bos": bear_bos,
                "sweeps": sweep_count,
                "ls_ratio": ls_ratio,
                "funding_rate": funding,
                "score": score,
                "lookback": self.lookback,
            },
            trap_probabilities={
                "stop_hunt_probability": stop_hunt_prob,
                "fake_breakout_probability": fake_breakout_prob,
                "short_squeeze_probability": short_squeeze_prob,
                "long_squeeze_probability": long_squeeze_prob,
            },
        )

    def _neutral(self, symbol: str, reason: str) -> TrapAnalysis:
        return TrapAnalysis(
            agent=self.name,
            symbol=symbol,
            bias="Neutral",
            confidence=0.0,
            reasoning=reason,
            evidence={},
            trap_probabilities={
                "stop_hunt_probability": 0.0,
                "fake_breakout_probability": 0.0,
                "short_squeeze_probability": 0.0,
                "long_squeeze_probability": 0.0,
            },
        )


__all__ = ["RetailTrapAgent", "TrapAnalysis"]
