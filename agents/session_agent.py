"""
agents.session_agent — Trading session detection + volume/volatility analysis.

Detects the current trading session from UTC time:
  - Asian       : 00:00–07:59 UTC
  - London      : 08:00–15:59 UTC
  - New York    : 16:00–23:59 UTC  (overlaps London 12:00–16:00 UTC, but we
                                    classify by primary slot for simplicity)

Analyzes the most recent bars within the current session and produces:
  - Session label + active flag
  - Average volume and ATR in this session vs the prior session
  - Bias: Bullish if current-session volume + ATR agree on direction
          Bearish if they disagree
          Neutral otherwise
  - Confidence proportional to relative volume + directional agreement

Output: AgentSignal with bias ∈ {Bullish, Bearish, Neutral}, confidence 0..100.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from agents.base_agent import AgentSignal, BaseAgent


# Session UTC hour boundaries (start_hour, end_hour_exclusive)
SESSIONS: dict[str, tuple[int, int]] = {
    "Asian":    (0, 8),
    "London":   (8, 16),
    "NewYork":  (16, 24),
}


def _session_for_utc(ts: datetime) -> str:
    """Return session label for a tz-aware UTC datetime."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    hour = ts.astimezone(timezone.utc).hour
    for label, (start, end) in SESSIONS.items():
        if start <= hour < end:
            return label
    return "Unknown"


class SessionAgent(BaseAgent):
    name = "session"
    description = "Trading session detection + volume/volatility analysis."

    def __init__(self, lookback_bars: int = 20) -> None:
        self.lookback_bars = lookback_bars

    async def analyze(
        self,
        symbol: str,
        features_df: pd.DataFrame | None = None,
        now_utc: datetime | None = None,
        **kwargs: Any,
    ) -> AgentSignal:
        if features_df is None or features_df.empty:
            return self._neutral(symbol, "No feature data provided.")

        required = {"volume", "close"}
        missing = required - set(features_df.columns)
        if missing:
            return self._neutral(
                symbol, f"Missing required columns: {missing}"
            )

        # Determine current session
        now = now_utc or datetime.now(timezone.utc)
        current_session = _session_for_utc(now)

        # Tag each bar with its session
        idx = features_df.index
        if not isinstance(idx, pd.DatetimeIndex):
            return self._neutral(symbol, "Feature DataFrame must have a DatetimeIndex.")
        sessions = idx.tz_convert("UTC").map(_session_for_utc) if idx.tz is not None \
                   else idx.tz_localize("UTC").map(_session_for_utc)
        sessions_arr = np.array(sessions)

        # Current vs prior session masks
        cur_mask = sessions_arr == current_session
        prior_label = self._prior_session(current_session)
        prior_mask = sessions_arr == prior_label

        if cur_mask.sum() < 3 or prior_mask.sum() < 3:
            return AgentSignal(
                agent=self.name,
                symbol=symbol,
                bias="Neutral",
                confidence=30.0,
                reasoning=(
                    f"Current session {current_session} (bars={cur_mask.sum()}) or "
                    f"prior session {prior_label} (bars={prior_mask.sum()}) has too few bars."
                ),
                evidence={
                    "current_session": current_session,
                    "prior_session": prior_label,
                    "current_bars": int(cur_mask.sum()),
                    "prior_bars": int(prior_mask.sum()),
                },
            )

        # Compute volume + ATR proxy for each session
        cur_df = features_df[cur_mask]
        prior_df = features_df[prior_mask]
        cur_vol = float(cur_df["volume"].mean())
        prior_vol = float(prior_df["volume"].mean())
        vol_ratio = cur_vol / prior_vol if prior_vol > 0 else 1.0

        # ATR proxy: mean high-low range
        if "atr_14" in features_df.columns:
            cur_atr = float(cur_df["atr_14"].dropna().mean() or 0.0)
            prior_atr = float(prior_df["atr_14"].dropna().mean() or 0.0)
        else:
            cur_atr = float((cur_df["high"] - cur_df["low"]).mean())
            prior_atr = float((prior_df["high"] - prior_df["low"]).mean())
        atr_ratio = cur_atr / prior_atr if prior_atr > 0 else 1.0

        # Direction: current session net price change
        cur_close = cur_df["close"].dropna()
        prior_close = prior_df["close"].dropna()
        if len(cur_close) >= 2:
            price_change_pct = (cur_close.iloc[-1] - cur_close.iloc[0]) / cur_close.iloc[0]
        else:
            price_change_pct = 0.0

        # Score: heavy volume + volatility + clear direction = high conviction
        score = 50.0
        reasons: list[str] = []
        if vol_ratio > 1.2:
            score += 10
            reasons.append(f"Volume {vol_ratio:.2f}x prior session (above average)")
        elif vol_ratio < 0.8:
            score -= 10
            reasons.append(f"Volume {vol_ratio:.2f}x prior session (below average)")
        else:
            reasons.append(f"Volume {vol_ratio:.2f}x prior session (typical)")

        if atr_ratio > 1.2:
            score += 10
            reasons.append(f"Volatility {atr_ratio:.2f}x prior session (expanded)")
        elif atr_ratio < 0.8:
            score -= 10
            reasons.append(f"Volatility {atr_ratio:.2f}x prior session (contracted)")

        if price_change_pct > 0.005:
            score += 15
            reasons.append(f"Session price change +{price_change_pct*100:.2f}% (bullish)")
        elif price_change_pct < -0.005:
            score -= 15
            reasons.append(f"Session price change {price_change_pct*100:.2f}% (bearish)")
        else:
            reasons.append(f"Session price change {price_change_pct*100:.2f}% (flat)")

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
                "current_session": current_session,
                "prior_session": prior_label,
                "current_bars": int(cur_mask.sum()),
                "prior_bars": int(prior_mask.sum()),
                "volume_ratio": vol_ratio,
                "volatility_ratio": atr_ratio,
                "session_price_change_pct": float(price_change_pct),
                "score": score,
            },
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _prior_session(current: str) -> str:
        order = ["Asian", "London", "NewYork"]
        try:
            i = order.index(current)
            return order[(i - 1) % len(order)]
        except ValueError:
            return "London"

    def _neutral(self, symbol: str, reason: str) -> AgentSignal:
        return AgentSignal(
            agent=self.name,
            symbol=symbol,
            bias="Neutral",
            confidence=0.0,
            reasoning=reason,
            evidence={},
        )


__all__ = ["SessionAgent", "SESSIONS", "_session_for_utc"]
