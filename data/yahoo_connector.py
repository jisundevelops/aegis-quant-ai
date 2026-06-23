"""
data.yahoo_connector — Yahoo Finance market data connector.

Uses the `yfinance` library. No API key required for basic usage.
Phase 2 implements the concrete body.
"""
from __future__ import annotations

import pandas as pd

from config import settings
from data.base_connector import BaseConnector


class YahooConnector(BaseConnector):
    """Yahoo Finance market data connector (equities, ETFs, FX, crypto)."""

    name = "yahoo"

    def __init__(self) -> None:
        self._user_agent = settings.yfinance_user_agent
        self._client = None  # Initialized in Phase 2.

    async def fetch_ohlcv(
        self,
        symbol: str,
        interval: str,
        limit: int = 500,
        start: pd.Timestamp | None = None,
        end: pd.Timestamp | None = None,
    ) -> pd.DataFrame:
        raise NotImplementedError("YahooConnector.fetch_ohlcv() lands in Phase 2.")

    async def fetch_symbols(self) -> list[dict]:
        raise NotImplementedError("YahooConnector.fetch_symbols() lands in Phase 2.")
