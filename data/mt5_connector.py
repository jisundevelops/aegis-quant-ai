"""
data.mt5_connector — MetaTrader 5 market data connector.

Uses the official `MetaTrader5` Python package. Requires the MT5 terminal
to be installed and reachable. Phase 2 implements the concrete body.
"""
from __future__ import annotations

import pandas as pd

from config import settings
from data.base_connector import BaseConnector


class MT5Connector(BaseConnector):
    """MetaTrader 5 market data connector (forex, CFDs, futures)."""

    name = "mt5"

    def __init__(self) -> None:
        self._login = settings.mt5_login
        self._password = settings.mt5_password
        self._server = settings.mt5_server
        self._path = settings.mt5_path
        self._client = None  # Initialized in Phase 2.

    async def fetch_ohlcv(
        self,
        symbol: str,
        interval: str,
        limit: int = 500,
        start: pd.Timestamp | None = None,
        end: pd.Timestamp | None = None,
    ) -> pd.DataFrame:
        raise NotImplementedError("MT5Connector.fetch_ohlcv() lands in Phase 2.")

    async def fetch_symbols(self) -> list[dict]:
        raise NotImplementedError("MT5Connector.fetch_symbols() lands in Phase 2.")

    async def close(self) -> None:
        if self._client is not None:
            # Phase 2: MetaTrader5.shutdown()
            self._client = None
