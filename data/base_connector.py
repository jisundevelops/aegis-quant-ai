"""
data.base_connector — Abstract base class for all market data connectors.

Every connector (Binance, Yahoo, MT5) implements this interface so that
the rest of the system is data-source agnostic.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

import pandas as pd


class BaseConnector(ABC):
    """Abstract base class for market data connectors."""

    name: str = "base"

    @abstractmethod
    async def fetch_ohlcv(
        self,
        symbol: str,
        interval: str,
        limit: int = 500,
        start: pd.Timestamp | None = None,
        end: pd.Timestamp | None = None,
    ) -> pd.DataFrame:
        """Return OHLCV bars as a DataFrame indexed by timestamp (UTC)."""
        raise NotImplementedError

    @abstractmethod
    async def fetch_symbols(self) -> list[dict]:
        """Return a list of tradable symbols with metadata."""
        raise NotImplementedError

    async def fetch_tick(self, symbol: str) -> AsyncIterator[dict]:
        """Stream ticks for `symbol`. Override in subclasses that support it."""
        raise NotImplementedError
        # The yield below is unreachable but signals the async generator
        # contract to type checkers.
        yield  # pragma: no cover

    async def close(self) -> None:
        """Release any underlying resources (sockets, sessions, etc.)."""
        return None

    @property
    def metadata(self) -> dict[str, str]:
        return {"connector": self.name, "version": "0.1.0"}

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r}>"
