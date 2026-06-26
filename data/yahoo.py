"""
data.yahoo — Yahoo Finance market data connector.

Fetches OHLCV bars for FX, commodities, and rates via the `yfinance`
library. yfinance is synchronous, so all calls are offloaded to a
thread pool to avoid blocking the asyncio event loop.

Pipeline:
  1. Pull bars for each (symbol, interval) pair.
  2. Validate each batch via `data.validator.DataValidator`.
  3. Upsert into the PostgreSQL `market_data` table.
  4. Cache the latest bar in Redis under `aegis:price:{symbol}:{tf}`
     with a 60-second TTL (per Phase 2 cache policy).

Symbols:
  - EURUSD=X        (EUR/USD spot)
  - XAUUSD=X        (Gold spot, USD per troy ounce)
  - DX-Y.NYB        (ICE U.S. Dollar Index — Yahoo's canonical ticker for DXY)
  - ^TNX            (US 10-year Treasury yield, percent)

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
# NOTE: XAUUSD=X was delisted from Yahoo Finance in 2024.
# GC=F (Gold Futures) is the closest valid replacement — it tracks
# the spot gold price and has full intraday history on Yahoo.
SYMBOLS: tuple[str, ...] = ("EURUSD=X", "GC=F", "DX-Y.NYB", "^TNX")
INTERVALS: tuple[str, str, str, str] = ("15m", "60m", "4h", "1d")

# Yahoo interval -> our market_data.timeframe canonical string
_YF_INTERVAL_MAP: dict[str, str] = {
    "15m": "15m",
    "60m": "1h",
    "4h": "4h",
    "1d": "1d",
}

# Period mapping: yfinance requires a `period` (or start/end) for intraday.
# 60d is the maximum supported period for 15m bars on Yahoo.
_YF_PERIOD: dict[str, str] = {
    "15m": "60d",
    "60m": "730d",   # ~2y — Yahoo's max for 1h
    "4h": "730d",
    "1d": "max",
}


class YahooConnector(BaseConnector):
    """Yahoo Finance market data connector (FX, commodities, rates)."""

    name = "yahoo"
    source = "yahoo"
    symbols = SYMBOLS
    intervals = INTERVALS

    def __init__(self) -> None:
        self._user_agent = settings.yfinance_user_agent
        self._client: Any = None  # yfinance is module-level, no client instance

    # ----------------------------------------------------------------
    # Lifecycle
    # ----------------------------------------------------------------
    async def close(self) -> None:
        # yfinance uses `requests` under the hood; nothing to close.
        return None

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
        """Fetch OHLCV bars from Yahoo Finance.

        Parameters
        ----------
        symbol   : e.g. "EURUSD=X"
        interval : Yahoo interval string ("15m","60m","4h","1d",...)
        limit    : desired number of bars (we over-fetch and tail-trim)
        start    : optional inclusive start (UTC)
        end      : optional inclusive end (UTC)

        Returns
        -------
        DataFrame indexed by timestamp (UTC, tz-aware) with columns:
            open, high, low, close, volume
        """
        if interval not in _YF_INTERVAL_MAP:
            raise ValueError(
                f"Unsupported Yahoo interval: {interval}. "
                f"Supported: {list(_YF_INTERVAL_MAP)}"
            )

        # yfinance is synchronous — run in default thread pool.
        df = await asyncio.to_thread(
            self._fetch_sync, symbol, interval, limit, start, end
        )
        return df

    # ----------------------------------------------------------------
    # Sync worker (runs in threadpool)
    # ----------------------------------------------------------------
    def _fetch_sync(
        self,
        symbol: str,
        interval: str,
        limit: int,
        start: pd.Timestamp | None,
        end: pd.Timestamp | None,
    ) -> pd.DataFrame:
        """Blocking yfinance call. MUST be invoked via asyncio.to_thread."""
        import yfinance as yf  # type: ignore

        kwargs: dict[str, Any] = {
            "interval": interval,
            "auto_adjust": False,
            "repair": True,
            "actions": False,
            # NOTE: 'threads' param was removed in yfinance >= 0.2.40.
            # Do NOT pass it — it causes:
            #   PriceHistory.history() got an unexpected keyword argument 'threads'
        }

        if start is not None and end is not None:
            kwargs["start"] = pd.Timestamp(start, tz="UTC").strftime("%Y-%m-%d")
            kwargs["end"] = (pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            # Use a generous period, then tail-trim to `limit`.
            kwargs["period"] = _YF_PERIOD.get(interval, "60d")

        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(**kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.error("yfinance history() failed for {} ({}): {}", symbol, interval, exc)
            return _empty_ohlcv()

        if df is None or df.empty:
            return _empty_ohlcv()

        # Normalise column names + index
        df = df.rename(columns=str.lower)
        needed = ["open", "high", "low", "close", "volume"]
        for col in needed:
            if col not in df.columns:
                df[col] = float("nan")
        df = df[needed]

        # Coerce index to UTC tz-aware
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")
        df.index.name = "timestamp"

        # Drop rows with NaN in price columns
        df = df.dropna(subset=["open", "high", "low", "close"])
        if df.empty:
            return _empty_ohlcv()

        # Tail-trim to limit
        if limit and len(df) > limit:
            df = df.iloc[-limit:]

        return df

    # ----------------------------------------------------------------
    # Batch helpers used by the scheduler
    # ----------------------------------------------------------------
    async def fetch_and_store_all(self, limit: int = 500) -> dict[str, int]:
        """Fetch all (symbol, interval) pairs and upsert into PostgreSQL."""
        from database.cache import cache_price
        from database.connection import async_session_ctx
        from database.models import MarketData
        from data.validator import DataValidator
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        validator = DataValidator()
        results: dict[str, int] = {}

        for symbol in self.symbols:
            for yf_interval in self.intervals:
                tf = _YF_INTERVAL_MAP[yf_interval]
                key = f"{symbol}:{tf}"
                try:
                    df = await self.fetch_ohlcv(symbol, yf_interval, limit=limit)
                except Exception as exc:  # noqa: BLE001
                    logger.error("Yahoo fetch failed for {}: {}", key, exc)
                    results[key] = 0
                    continue

                if df.empty:
                    logger.warning("Yahoo returned no rows for {}", key)
                    results[key] = 0
                    continue

                # Validate
                report = validator.validate(df, symbol=symbol, timeframe=tf)
                if report.has_errors:
                    logger.warning(
                        "Yahoo validation errors for {}: {}", key, report.error_summary
                    )
                if report.has_warnings:
                    logger.warning(
                        "Yahoo validation warnings for {}: {}", key, report.warning_summary
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

                # Cache latest bar in Redis
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
                logger.info("Yahoo stored {} rows for {}", stored, key)

        return results

    async def fetch_symbols(self) -> list[dict]:
        """Yahoo has no enumerable symbol list — return the configured symbols."""
        return [{"symbol": s, "exchange": "yahoo", "asset_class": _classify(s)} for s in self.symbols]


# --------------------------------------------------------------------
# Module-level helpers
# --------------------------------------------------------------------
def _classify(symbol: str) -> str:
    """Best-effort asset-class tag for the configured Yahoo symbols."""
    if symbol.endswith("=X") and "XAU" not in symbol:
        return "fx"
    if symbol in ("XAUUSD=X", "GC=F", "GLD"):  # Gold (spot or futures or ETF)
        return "commodity"
    if symbol.startswith("^"):
        return "rate"
    if "DX-Y" in symbol:
        return "index"
    return "unknown"


def _empty_ohlcv() -> pd.DataFrame:
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


__all__ = ["YahooConnector", "SYMBOLS", "INTERVALS"]
