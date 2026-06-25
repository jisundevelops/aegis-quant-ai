"""
chief.chief_agent — Chief Agent (Phase 6).

Orchestrates all 8 Phase 5 agents, weights their confidence scores per
the Phase 6 spec, and produces the final Aegis signal.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

from agents.base_agent import AgentSignal
from agents.derivatives_agent import DerivativesAgent
from agents.macro_agent import MacroAgent
from agents.retail_trap_agent import RetailTrapAgent
from agents.risk_agent import RiskAgent, TradePlan
from agents.session_agent import SessionAgent
from agents.smc_agent import SMCAgent
from agents.sentiment_agent import SentimentAgent
from agents.trend_agent import TrendAgent
from probability.probability_engine import (
    ProbabilityEngine,
    ScenarioProbabilities,
)


AGENT_WEIGHTS: dict[str, float] = {
    "trend":        0.20,
    "smc":          0.25,
    "derivatives":  0.20,
    "macro":        0.10,
    "session":      0.05,
    "sentiment":    0.05,
    "retail_trap":  0.15,
}

BULL_THRESHOLD = 60.0
BEAR_THRESHOLD = 40.0


@dataclass
class ChiefSignal:
    """Final output of the Chief Agent."""

    symbol: str
    timeframe: str
    direction: str
    entry_zone: tuple[float, float] | None
    stop_loss: float | None
    take_profit_1: float | None
    take_profit_2: float | None
    risk_score: float
    confidence_score: float
    reasoning: str
    agent_breakdown: dict[str, dict[str, Any]]
    probabilities: dict[str, Any]
    trade_plan: dict[str, Any] | None = None
    timestamp: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "direction": self.direction,
            "entry_zone": list(self.entry_zone) if self.entry_zone else None,
            "stop_loss": self.stop_loss,
            "take_profit_1": self.take_profit_1,
            "take_profit_2": self.take_profit_2,
            "risk_score": round(self.risk_score, 2),
            "confidence_score": round(self.confidence_score, 2),
            "reasoning": self.reasoning,
            "agent_breakdown": self.agent_breakdown,
            "probabilities": self.probabilities,
            "trade_plan": self.trade_plan,
            "timestamp": self.timestamp,
        }


class ChiefAgent:
    """Orchestrates all Phase 5 agents and produces the final signal."""

    name: str = "chief"

    def __init__(
        self,
        weights: dict[str, float] | None = None,
        probability_engine: ProbabilityEngine | None = None,
        risk_agent: RiskAgent | None = None,
    ) -> None:
        self.weights = weights or AGENT_WEIGHTS.copy()
        self.probability_engine = probability_engine or ProbabilityEngine()
        self.risk_agent = risk_agent or RiskAgent()
        self.trend_agent = TrendAgent()
        self.smc_agent = SMCAgent()
        self.derivatives_agent = DerivativesAgent()
        self.macro_agent = MacroAgent()
        self.session_agent = SessionAgent()
        self.sentiment_agent = SentimentAgent()
        self.retail_trap_agent = RetailTrapAgent()

    async def analyze(
        self,
        symbol: str,
        timeframe: str,
        features_df: pd.DataFrame,
        dxy_df: pd.DataFrame | None = None,
        us10y_df: pd.DataFrame | None = None,
        capital: float = 10_000.0,
    ) -> ChiefSignal:
        from datetime import datetime, timezone
        timestamp = datetime.now(timezone.utc).isoformat()

        signals: dict[str, AgentSignal] = {}
        try:
            results = await asyncio.gather(
                self.trend_agent.analyze(symbol, features_df=features_df),
                self.smc_agent.analyze(symbol, features_df=features_df),
                self.derivatives_agent.analyze(symbol, features_df=features_df),
                self.macro_agent.analyze(symbol, features_df=features_df,
                                          dxy_df=dxy_df, us10y_df=us10y_df),
                self.session_agent.analyze(symbol, features_df=features_df),
                self.sentiment_agent.analyze(symbol),
                self.retail_trap_agent.analyze(symbol, features_df=features_df),
                return_exceptions=True,
            )
            for r in results:
                if isinstance(r, Exception):
                    logger.error("Agent raised: {}", r)
                    continue
                signals[r.agent] = r
        except Exception as exc:
            logger.exception("Chief Agent fan-out failed: {}", exc)

        if not signals:
            return self._neutral_signal(symbol, timeframe, timestamp,
                                         "All agents failed to produce signals.")

        weighted_score = 50.0
        agent_breakdown: dict[str, dict[str, Any]] = {}
        for name, sig in signals.items():
            w = self.weights.get(name, 0.0)
            if sig.bias == "Bullish":
                signed = sig.confidence
            elif sig.bias == "Bearish":
                signed = -sig.confidence
            else:
                signed = 0.0
            contribution = w * signed
            weighted_score += contribution
            agent_breakdown[name] = {
                "bias": sig.bias,
                "confidence": round(sig.confidence, 2),
                "weight": round(w, 4),
                "weighted_contribution": round(contribution, 2),
                "reasoning": sig.reasoning,
            }

        weighted_score = float(np.clip(weighted_score, 0.0, 100.0))

        if weighted_score >= BULL_THRESHOLD:
            direction = "LONG"
        elif weighted_score <= BEAR_THRESHOLD:
            direction = "SHORT"
        else:
            direction = "NEUTRAL"

        confidence_score = float(np.clip(abs(weighted_score - 50.0) * 2.0, 0.0, 100.0))

        signals_list = list(signals.values())
        probs: ScenarioProbabilities = self.probability_engine.compute(
            signals_list, weights=self.weights
        )

        entry = float(features_df["close"].iloc[-1]) if "close" in features_df.columns and not features_df.empty else None
        atr = None
        if "atr_14" in features_df.columns:
            atr_series = features_df["atr_14"].dropna()
            if not atr_series.empty:
                atr = float(atr_series.iloc[-1])

        trade_plan: TradePlan | None = None
        if entry is not None and atr is not None and atr > 0:
            bias_for_risk = {"LONG": "Bullish", "SHORT": "Bearish", "NEUTRAL": "Neutral"}[direction]
            trade_plan = await self.risk_agent.analyze(
                symbol,
                features_df=features_df,
                entry=entry,
                direction=bias_for_risk,
                atr=atr,
                capital=capital,
                conviction=confidence_score,
            )

        if entry is not None and direction != "NEUTRAL":
            entry_zone = (round(entry * 0.999, 6), round(entry * 1.001, 6))
        else:
            entry_zone = None

        reasoning = self._build_reasoning(signals, weighted_score, direction, probs)

        risk_score = trade_plan.trade_safety_score if trade_plan else 0.0

        return ChiefSignal(
            symbol=symbol,
            timeframe=timeframe,
            direction=direction,
            entry_zone=entry_zone,
            stop_loss=trade_plan.stop_loss if trade_plan else None,
            take_profit_1=trade_plan.take_profit_1 if trade_plan else None,
            take_profit_2=trade_plan.take_profit_2 if trade_plan else None,
            risk_score=risk_score,
            confidence_score=confidence_score,
            reasoning=reasoning,
            agent_breakdown=agent_breakdown,
            probabilities=probs.as_dict(),
            trade_plan=trade_plan.model_dump() if trade_plan else None,
            timestamp=timestamp,
        )

    def _build_reasoning(
        self,
        signals: dict[str, AgentSignal],
        weighted_score: float,
        direction: str,
        probs: ScenarioProbabilities,
    ) -> str:
        parts: list[str] = []
        parts.append(
            f"Chief Agent weighted score: {weighted_score:.1f}/100 -> direction {direction}."
        )
        parts.append(
            f"Scenario probabilities: Bull {probs.bull_pct:.1f}% / "
            f"Bear {probs.bear_pct:.1f}% / Range {probs.range_pct:.1f}%."
        )
        parts.append("Agent summaries:")
        ordered = sorted(
            signals.items(),
            key=lambda kv: self.weights.get(kv[0], 0.0),
            reverse=True,
        )
        for name, sig in ordered:
            w = self.weights.get(name, 0.0)
            parts.append(
                f"  [{name} ({w*100:.0f}% weight)] {sig.bias} "
                f"(confidence {sig.confidence:.1f}): {sig.reasoning}"
            )
        return "\n".join(parts)

    def _neutral_signal(
        self, symbol: str, timeframe: str, timestamp: str, reason: str
    ) -> ChiefSignal:
        return ChiefSignal(
            symbol=symbol,
            timeframe=timeframe,
            direction="NEUTRAL",
            entry_zone=None,
            stop_loss=None,
            take_profit_1=None,
            take_profit_2=None,
            risk_score=0.0,
            confidence_score=0.0,
            reasoning=reason,
            agent_breakdown={},
            probabilities={
                "bull_pct": 100 / 3, "bear_pct": 100 / 3, "range_pct": 100 / 3,
                "sum_pct": 100.0, "contributions": {}, "explanation": reason,
            },
            trade_plan=None,
            timestamp=timestamp,
        )


__all__ = ["ChiefAgent", "ChiefSignal", "AGENT_WEIGHTS"]
