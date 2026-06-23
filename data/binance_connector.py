"""
data.binance_connector — Binance market data connector.

Uses the `python-binance` SDK. Phase 2 implements the full body; today
this module ships the constructor signature, settings wiring, and an
explicit NotImplementedError so the rest of the system can import it
without crashing.
"""
from __future__ import annotations

import pandas as pd

from config import settings
from data.base_connector import BaseConnector


class BinanceConnector(BaseConnector):
    """Binance spot + futures market data connector."""

    name = "binance"

    def __init__(self) -> None:
        self._api_key = settings.binance_api_key
        self._api_secret = settings.binance_api_secret
        self._testnet = settings.binance_testnet
        self._client = None  # Initialized in Phase 2.

    async def fetch_ohlcv(
        self,
        symbol: str,
        interval: str,
        limit: int = 500,
        start: pd.Timestamp | None = None,
        end: pd.Timestamp | None = None,
    ) -> pd.DataFrame:
        raise NotImplementedError("BinanceConnector.fetch_ohlcv() lands in Phase 2.")

    async def fetch_symbols(self) -> list[dict]:
        raise NotImplementedError("BinanceConnector.fetch_symbols() lands in Phase 2.")

    async def close(self) -> None:
        if self._client is not None:
            # Phase 2: await self._client.close_connection()
            self._client = None
