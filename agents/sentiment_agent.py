"""
agents.sentiment_agent — News / social sentiment agent (placeholder).

Phase 5 spec: return Neutral with confidence 50.

TODO (future phase): integrate a real news/sentiment API:
  - NewsAPI (https://newsapi.org/) for headlines
  - Alpha Vantage News Sentiment (https://www.alphavantage.co/)
  - CryptoPanic (https://cryptopanic.com/) for crypto headlines
  - Twitter/X filtered stream (via Official API v2)
  - Reddit (r/cryptocurrency, r/wallstreetbets) via PRAW

The integration plan:
  1. Fetch the latest N headlines / posts mentioning the symbol.
  2. Run each through a sentiment classifier (e.g. VADER, FinBERT, or
     an LLM provider from config.openai_api_key / anthropic_api_key).
  3. Aggregate per-item sentiment into a single score in [-1, +1].
  4. Map: score > +0.2 -> Bullish, score < -0.2 -> Bearish, else Neutral.
  5. Confidence = |score| * 100, clamped to [0, 100].

This file replaces the Phase 1 stub. The class name `SentimentAgent` and
`name = "sentiment"` are preserved so Phase 1 imports + tests still pass.
"""
from __future__ import annotations

from typing import Any

from agents.base_agent import AgentSignal, BaseAgent


class SentimentAgent(BaseAgent):
    """Placeholder sentiment agent — returns Neutral/50 until news API is wired."""

    name = "sentiment"
    description = "News + social sentiment agent (placeholder; Neutral/50)."

    async def analyze(
        self,
        symbol: str,
        **kwargs: Any,
    ) -> AgentSignal:
        return AgentSignal(
            agent=self.name,
            symbol=symbol,
            bias="Neutral",
            confidence=50.0,
            reasoning=(
                "Sentiment agent is a placeholder in Phase 5. "
                "Returns Neutral with confidence 50. "
                "TODO: integrate NewsAPI / Alpha Vantage / CryptoPanic / X / Reddit."
            ),
            evidence={
                "status": "placeholder",
                "todo": "Wire news API + NLP classifier in a future phase.",
            },
        )


__all__ = ["SentimentAgent"]
