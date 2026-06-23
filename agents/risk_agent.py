"""
agents.risk_agent — Risk + position sizing agent.

Inputs:
  - entry price
  - direction (Bullish/Bearish/Neutral)
  - ATR (volatility proxy)

Computes:
  - Stop Loss  : entry ∓ 1.5 * ATR (against the position direction)
  - TP1        : entry ± 1.0 * R  (where R = entry - SL distance)
  - TP2        : entry ± 2.0 * R
  - Position size: based on 1% account risk rule (capital * 0.01 / R per unit)
  - Risk/Reward ratio: |TP1 - entry| / |entry - SL|
  - Trade Safety Score: 0..100 (higher = safer trade)

Output: AgentSignal subclass `TradePlan` with all the trade parameters.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from pydantic import Field

from agents.base_agent import AgentSignal, BaseAgent


class TradePlan(AgentSignal):
    """Output of the risk agent — bias + concrete trade plan."""

    entry: float | None = None
    stop_loss: float | None = None
    take_profit_1: float | None = None
    take_profit_2: float | None = None
    position_size: float | None = Field(default=None, description="Units to trade (1% risk rule)")
    risk_per_unit: float | None = Field(default=None, description="|entry - SL| per unit of the asset")
    risk_reward_ratio: float | None = Field(default=None, description="R/R to TP1")
    trade_safety_score: float = Field(default=0.0, ge=0.0, le=100.0,
        description="0..100 — higher is safer. Considers R/R, ATR-normalized risk, and direction conviction.")


class RiskAgent(BaseAgent):
    name = "risk"
    description = "Risk + position sizing agent (SL/TP1/TP2/size/RR/safety)."

    # Default capital (overridable via kwarg)
    DEFAULT_CAPITAL = 10_000.0
    # 1% risk rule
    RISK_PCT = 0.01
    # Stop distance in ATR units
    STOP_ATR_MULT = 1.5
    # TP1 = 1R, TP2 = 2R
    TP1_R_MULT = 1.0
    TP2_R_MULT = 2.0

    async def analyze(
        self,
        symbol: str,
        features_df: pd.DataFrame | None = None,
        entry: float | None = None,
        direction: str | None = None,
        atr: float | None = None,
        capital: float | None = None,
        conviction: float | None = None,
        **kwargs: Any,
    ) -> TradePlan:
        """Compute a trade plan.

        Parameters
        ----------
        symbol       : ticker
        features_df  : optional feature frame (used to look up entry/close + atr_14 if not provided)
        entry        : explicit entry price (defaults to latest close from features_df)
        direction    : 'Bullish' | 'Bearish' | 'Neutral' (defaults to Neutral)
        atr          : explicit ATR (defaults to latest atr_14 from features_df)
        capital      : account capital for sizing (defaults to DEFAULT_CAPITAL)
        conviction   : 0..100 conviction from the Chief Agent (affects safety score)
        """
        # Resolve entry / atr from features_df if not provided
        if entry is None and features_df is not None and not features_df.empty and "close" in features_df.columns:
            entry = float(features_df["close"].iloc[-1])
        if atr is None and features_df is not None and not features_df.empty and "atr_14" in features_df.columns:
            atr_series = features_df["atr_14"].dropna()
            if not atr_series.empty:
                atr = float(atr_series.iloc[-1])

        if entry is None or atr is None or atr <= 0:
            return self._neutral(
                symbol,
                f"Cannot compute trade plan without entry + ATR. "
                f"(entry={entry}, atr={atr})",
            )

        bias = self._normalize_direction(direction)
        cap = capital if capital is not None and capital > 0 else self.DEFAULT_CAPITAL
        conv = float(np.clip(conviction if conviction is not None else 50.0, 0.0, 100.0))

        # Compute SL + TPs based on direction
        if bias == "Bullish":
            stop_loss = entry - self.STOP_ATR_MULT * atr
            r = entry - stop_loss
            tp1 = entry + self.TP1_R_MULT * r
            tp2 = entry + self.TP2_R_MULT * r
        elif bias == "Bearish":
            stop_loss = entry + self.STOP_ATR_MULT * atr
            r = stop_loss - entry
            tp1 = entry - self.TP1_R_MULT * r
            tp2 = entry - self.TP2_R_MULT * r
        else:  # Neutral
            return TradePlan(
                agent=self.name,
                symbol=symbol,
                bias="Neutral",
                confidence=0.0,
                reasoning="Direction is Neutral — no trade plan issued.",
                evidence={"entry": entry, "atr": atr, "direction": "Neutral"},
                entry=entry,
                stop_loss=None,
                take_profit_1=None,
                take_profit_2=None,
                position_size=0.0,
                risk_per_unit=0.0,
                risk_reward_ratio=0.0,
                trade_safety_score=0.0,
            )

        # Position size: 1% of capital / risk per unit
        risk_amount = cap * self.RISK_PCT
        position_size = risk_amount / r if r > 0 else 0.0

        # R/R ratio to TP1
        rr_ratio = self.TP1_R_MULT  # = 1.0 by construction; include for clarity

        # Trade Safety Score: 0..100
        # Components:
        #   - R/R component (40 pts max): rr_ratio of 1.0 = 30 pts, 2.0 = 40 pts
        #   - Conviction component (30 pts): scaled 0..1 from conviction 0..100
        #   - ATR-normalised risk component (30 pts): smaller SL/entry ratio = safer
        rr_pts = min(40.0, 30.0 * rr_ratio)
        conv_pts = 30.0 * (conv / 100.0)
        sl_to_entry = abs(stop_loss - entry) / entry if entry > 0 else 1.0
        # SL within 1% of entry = 30 pts; within 3% = 15 pts; >5% = 0 pts
        if sl_to_entry <= 0.01:
            atr_pts = 30.0
        elif sl_to_entry <= 0.03:
            atr_pts = 20.0
        elif sl_to_entry <= 0.05:
            atr_pts = 10.0
        else:
            atr_pts = 0.0
        safety = float(np.clip(rr_pts + conv_pts + atr_pts, 0.0, 100.0))

        # Map safety to confidence for the AgentSignal base
        confidence = safety  # the safety score IS the agent's confidence in the trade

        reasons = [
            f"Entry: {entry:.4f}",
            f"Direction: {bias}",
            f"ATR: {atr:.4f}",
            f"SL: {stop_loss:.4f} ({self.STOP_ATR_MULT}x ATR)",
            f"TP1: {tp1:.4f} ({self.TP1_R_MULT}R)",
            f"TP2: {tp2:.4f} ({self.TP2_R_MULT}R)",
            f"Position size: {position_size:.4f} units (1% of {cap:.0f} capital)",
            f"R/R to TP1: {rr_ratio:.2f}",
            f"Trade safety score: {safety:.1f}/100 (R/R={rr_pts:.0f}, conv={conv_pts:.0f}, ATR={atr_pts:.0f})",
        ]

        return TradePlan(
            agent=self.name,
            symbol=symbol,
            bias=bias,
            confidence=confidence,
            reasoning="; ".join(reasons),
            evidence={
                "entry": entry,
                "atr": atr,
                "stop_loss": stop_loss,
                "tp1": tp1,
                "tp2": tp2,
                "position_size": position_size,
                "risk_per_unit": r,
                "risk_reward_ratio": rr_ratio,
                "trade_safety_score": safety,
                "capital": cap,
                "conviction": conv,
                "stop_atr_mult": self.STOP_ATR_MULT,
            },
            entry=entry,
            stop_loss=stop_loss,
            take_profit_1=tp1,
            take_profit_2=tp2,
            position_size=position_size,
            risk_per_unit=r,
            risk_reward_ratio=rr_ratio,
            trade_safety_score=safety,
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_direction(direction: str | None) -> str:
        if direction is None:
            return "Neutral"
        d = direction.strip().lower()
        if d in {"bullish", "long", "buy", "bull"}:
            return "Bullish"
        if d in {"bearish", "short", "sell", "bear"}:
            return "Bearish"
        return "Neutral"

    def _neutral(self, symbol: str, reason: str) -> TradePlan:
        return TradePlan(
            agent=self.name,
            symbol=symbol,
            bias="Neutral",
            confidence=0.0,
            reasoning=reason,
            evidence={},
            trade_safety_score=0.0,
        )


__all__ = ["RiskAgent", "TradePlan"]
