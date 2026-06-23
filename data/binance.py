"""
data.binance — Binance market data connector (public REST endpoints).

Fetches OHLCV bars for the configured symbols and timeframes via the
`python-binance` AsyncClient. No API key required — public market data
endpoints are used. The connector:
  1. Pulls klines for each (symbol, interval) pair.
  2. Validates each batch via `data.validator.DataValidator`.
  3. Upserts into the PostgreSQL `market_data` table.
  4. Caches the latest bar in Redis under `aegis:price:{symbol}:{tf}`
     with a 60-second TTL (per Phase 2 cache policy).

Symbols : BTCUSDT, ETHUSDT
Intervals: 15m, 1h, 4h, 1d
"""
from __future__ import annotations

import asyncio
from typing import Any

import pandas as pd
from loguru import logger

from config import settings
from data.base_connector import BaseConnector

# --------------------------------------------------------------------
# Static configuration (Phase 3 spec)
# --------------------------------------------------------------------
SYMBOLS: tuple[str, ...] = ("BTCUSDT", "ETHUSDT")
INTERVALS: tuple[str, ...] = ("15m", "1h", "4h", "1d")

# Binance interval -> our market_data.timeframe canonical string
# (they happen to match Binance, but normalising here keeps the door open)
_INTERVAL_MAP: dict[str, str] = {
    "15m": "15m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
}


class BinanceConnector(BaseConnector):
    """Binance spot public market data connector.

    Uses `python-binance.AsyncClient` with no API key — only public
    endpoints are touched. If `BINANCE_API_KEY`/`BINANCE_API_SECRET`
    are configured in `.env`, they're still forwarded to the client
    (raises rate limits) but are not required.
    """

    name = "binance"
    source = "binance"
    symbols = SYMBOLS
    intervals = INTERVALS

    def __init__(self) -> None:
        # Credentials are optional. Public endpoints don't require them.
        self._api_key = settings.binance_api_key or None
        self._api_secret = settings.binance_api_secret or None
        self._testnet = settings.binance_testnet
        self._client: Any = None  # binance.AsyncClient

    # ----------------------------------------------------------------
    # Lifecycle
    # ----------------------------------------------------------------
    async def _ensure_client(self) -> Any:
        """Lazily build the AsyncClient on first use."""
        if self._client is None:
            # Local import so the module imports cleanly even if
            # python-binance is not installed (tests can mock around it).
            from binance import AsyncClient  # type: ignore

            self._client = await AsyncClient.create(
                api_key=self._api_key,
                api_secret=self._api_secret,
                testnet=self._testnet,
            )
            logger.info("Binance AsyncClient connected (testnet={})", self._testnet)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.close_connection()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Binance close_connection error: {}", exc)
            self._client = None

    # ----------------------------------------------------------------
    # Core fetch (single symbol/interval)
    # ----------------------------------------------------------------
    async def fetch_ohlcv(
        self,
        symbol: str,
        interval: str,
        limit: int = 500,
        start: pd.Timestamp | None = None,
        end: pd.Timestamp | None = None,
    ) -> pd.DataFrame:
        """Fetch OHLCV bars from Binance.

        Parameters
        ----------
        symbol   : e.g. "BTCUSDT"
        interval : one of Binance intervals ("15m","1h","4h","1d",...)
        limit    : number of bars (max 1000 on Binance public endpoint)
        start    : optional inclusive start (UTC)
        end      : optional inclusive end (UTC)

        Returns
        -------
        DataFrame indexed by timestamp (UTC, tz-aware) with columns:
            open, high, low, close, volume
        """
        if limit < 1 or limit > 1000:
            raise ValueError(f"limit must be in [1, 1000], got {limit}")

        client = await self._ensure_client()

        kwargs: dict[str, Any] = {"limit": limit}
        if start is not None:
            kwargs["startTime"] = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
        if end is not None:
            kwargs["endTime"] = int(pd.Timestamp(end, tz="UTC").timestamp() * 1000)

        # Public endpoint — klines. Works without API key.
        raw = await client.get_klines(symbol=symbol, interval=interval, **kwargs)
        if not raw:
            return _empty_ohlcv()

        df = pd.DataFrame(
            raw,
            columns=[
                "open_time", "open", "high", "low", "close", "volume",
                "close_time", "quote_volume", "trades",
                "taker_buy_base", "taker_buy_quote", "ignore",
            ],
        )
        # Convert types
        for col in ("open", "high", "low", "close", "volume"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        # Index by UTC open_time
        df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        df = df[["timestamp", "open", "high", "low", "close", "volume"]]
        df = df.dropna(subset=["open", "high", "low", "close"]).set_index("timestamp")
        return df

    async def fetch_symbols(self) -> list[dict]:
        """Return Binance exchange info (symbols list)."""
        client = await self._ensure_client()
        info = await client.get_exchange_info()
        return [
            {
                "symbol": s["symbol"],
                "base": s.get("baseAsset"),
                "quote": s.get("quoteAsset"),
                "status": s.get("status"),
            }
            for s in info.get("symbols", [])
        ]

    # ----------------------------------------------------------------
    # Batch helpers used by the scheduler
    # ----------------------------------------------------------------
    async def fetch_and_store_all(self, limit: int = 500) -> dict[str, int]:
        """Fetch all (symbol, interval) pairs and upsert into PostgreSQL.

        Returns a dict mapping "{symbol}:{interval}" -> number of rows stored.
        """
        from database.cache import cache_price
        from database.connection import async_session_ctx
        from database.models import MarketData
        from data.validator import DataValidator
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        validator = DataValidator()
        results: dict[str, int] = {}

        for symbol in self.symbols:
            for interval in self.intervals:
                key = f"{symbol}:{interval}"
                try:
                    df = await self.fetch_ohlcv(symbol, interval, limit=limit)
                except Exception as exc:  # noqa: BLE001
                    logger.error("Binance fetch failed for {}: {}", key, exc)
                    results[key] = 0
                    continue

                if df.empty:
                    logger.warning("Binance returned no rows for {}", key)
                    results[key] = 0
                    continue

                # Validate
                tf = _INTERVAL_MAP[interval]
                report = validator.validate(df, symbol=symbol, timeframe=tf)
                if report.has_errors:
                    logger.warning(
                        "Binance validation errors for {}: {}",
                        key, report.error_summary,
                    )
                if report.has_warnings:
                    logger.warning(
                        "Binance validation warnings for {}: {}",
                        key, report.warning_summary,
                    )

                # Upsert into PostgreSQL
                rows = _df_to_rows(df, symbol=symbol, timeframe=tf, source=self.source)
                stored = 0
                try:
                    async with async_session_ctx() as session:
                        stmt = pg_insert(MarketData).values(rows)
                        stmt = stmt.on_conflict_do_update(
                            constraint="uq_market_data_symbol_tf_ts",
                            set_={
                                "open": stmt.excluded.open,
                                "high": stmt.excluded.high,
                                "low": stmt.excluded.low,
                                "close": stmt.excluded.close,
                                "volume": stmt.excluded.volume,
                                "source": stmt.excluded.source,
                            },
                        )
                        await session.execute(stmt)
                        await session.commit()
                        stored = len(rows)
                except Exception as exc:  # noqa: BLE001
                    logger.error("PostgreSQL upsert failed for {}: {}", key, exc)
                    results[key] = 0
                    continue

                # Cache latest bar in Redis (60s TTL — Phase 2 policy)
                if not df.empty:
                    latest = df.iloc[-1]
                    await cache_price(
                        symbol,
                        {
                            "symbol": symbol,
                            "timeframe": tf,
                            "timestamp": df.index[-1].isoformat(),
                            "open": float(latest["open"]),
                            "high": float(latest["high"]),
                            "low": float(latest["low"]),
                            "close": float(latest["close"]),
                            "volume": float(latest["volume"]),
                            "source": self.source,
                        },
                        timeframe=tf,
                    )

                results[key] = stored
                logger.info("Binance stored {} rows for {}", stored, key)

        return results


# --------------------------------------------------------------------
# Module-level helpers
# --------------------------------------------------------------------
def _empty_ohlcv() -> pd.DataFrame:
    """Return an empty OHLCV DataFrame with the right columns + index."""
    return pd.DataFrame(
        columns=["open", "high", "low", "close", "volume"]
    ).astype(float)


def _df_to_rows(
    df: pd.DataFrame, *, symbol: str, timeframe: str, source: str
) -> list[dict]:
    """Convert an OHLCV DataFrame to a list of MarketData row dicts."""
    rows: list[dict] = []
    for ts, row in df.iterrows():
        rows.append({
            "symbol": symbol,
            "timeframe": timeframe,
            "timestamp": ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
            "source": source,
        })
    return rows


__all__ = ["BinanceConnector", "SYMBOLS", "INTERVALS"]
