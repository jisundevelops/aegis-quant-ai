"""
features.combiner — Merge all features into one frame per symbol/timeframe.

Pipeline:
  1. Load OHLCV bars from PostgreSQL `market_data` table for the given
     (symbol, timeframe).
  2. Compute TechnicalFeatures (sync, pandas-ta).
  3. Compute SmartMoneyFeatures (sync, pure pandas/numpy).
  4. Compute DerivativesFeatures (async, Binance Futures API) — best
     effort; failure is logged and we continue without derivatives.
  5. Validate the final DataFrame — no fully-NaN feature columns, no
     duplicate column names.
  6. Cache the combined frame to Redis under
     `aegis:features:{symbol}:{tf}` with the Phase 2 FEATURE_TTL (300s).

Usage:
    combiner = FeatureCombiner()
    df = await combiner.build("BTCUSDT", "1h", limit=500)
"""
from __future__ import annotations

import json
from typing import Any

import pandas as pd
from loguru import logger
from sqlalchemy import select

from database.cache import FEATURE_TTL, cache_features, get_features
from database.connection import async_session_ctx
from database.models import MarketData
from features.derivatives import DerivativesFeatures
from features.smc import SmartMoneyFeatures
from features.technical import TechnicalFeatures


class FeatureCombiner:
    """Build a combined feature DataFrame for one (symbol, timeframe)."""

    def __init__(
        self,
        technical: TechnicalFeatures | None = None,
        smc: SmartMoneyFeatures | None = None,
        derivatives: DerivativesFeatures | None = None,
    ) -> None:
        self.technical = technical or TechnicalFeatures()
        self.smc = smc or SmartMoneyFeatures()
        self.derivatives = derivatives or DerivativesFeatures()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def build(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 500,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """Return the combined feature DataFrame.

        Parameters
        ----------
        symbol    : e.g. "BTCUSDT"
        timeframe : "15m" | "1h" | "4h" | "1d"
        limit     : number of bars to pull from market_data
        use_cache : if True, return cached frame from Redis when fresh
        """
        # 0. Cache lookup
        if use_cache:
            cached = await get_features(symbol, timeframe)
            if cached is not None and "data" in cached:
                try:
                    df = pd.DataFrame(cached["data"])
                    if not df.empty:
                        logger.info(
                            "FeatureCombiner cache HIT for {}:{} ({} rows)",
                            symbol, timeframe, len(df),
                        )
                        return df
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Cache decode failed for {}:{}: {}",
                                   symbol, timeframe, exc)

        # 1. Load OHLCV
        df = await self._load_ohlcv(symbol, timeframe, limit)
        if df.empty:
            logger.warning("No market_data for {}:{}", symbol, timeframe)
            return df

        # 2. Technical features (sync)
        df = self.technical.compute(df)
        logger.info("Technical features computed for {}:{}", symbol, timeframe)

        # 3. SMC features (sync)
        df = self.smc.compute(df)
        logger.info("SMC features computed for {}:{}", symbol, timeframe)

        # 4. Derivatives (async, best-effort)
        try:
            df = await self.derivatives.compute_async(df, symbol=symbol)
            logger.info("Derivatives features computed for {}:{}", symbol, timeframe)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Derivatives features skipped for {}:{}: {}",
                symbol, timeframe, exc,
            )

        # 5. Validate
        self._validate(df, symbol=symbol, timeframe=timeframe)

        # 6. Cache (skip categorical columns — they don't serialise cleanly)
        if use_cache:
            await self._cache(df, symbol, timeframe)

        return df

    # ------------------------------------------------------------------
    # Loaders
    # ------------------------------------------------------------------
    async def _load_ohlcv(
        self, symbol: str, timeframe: str, limit: int
    ) -> pd.DataFrame:
        """Pull OHLCV from PostgreSQL market_data table."""
        try:
            async with async_session_ctx() as session:
                stmt = (
                    select(
                        MarketData.timestamp,
                        MarketData.open,
                        MarketData.high,
                        MarketData.low,
                        MarketData.close,
                        MarketData.volume,
                    )
                    .where(MarketData.symbol == symbol)
                    .where(MarketData.timeframe == timeframe)
                    .order_by(MarketData.timestamp.desc())
                    .limit(limit)
                )
                rows = (await session.execute(stmt)).all()
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "PostgreSQL load failed for {}:{}: {}\n"
                "  → Check GET /api/admin/diagnose for full diagnostic.\n"
                "  → Common fixes:\n"
                "    1. Verify DATABASE_URL is set on Render (postgresql+asyncpg://...)\n"
                "    2. Verify Supabase project is not paused (free tier auto-pauses)\n"
                "    3. Call POST /api/admin/fetch-data to populate market_data",
                symbol, timeframe, exc
            )
            return pd.DataFrame()

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df = df.sort_values("timestamp").set_index("timestamp")
        # Ensure tz-aware
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        return df

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def _validate(self, df: pd.DataFrame, *, symbol: str, timeframe: str) -> None:
        """Sanity-check the combined DataFrame.

        - No duplicate columns.
        - No entirely-NaN feature column (initial NaN warm-up is allowed).
        - Index is unique + monotonic increasing.

        Logs warnings for any issue found. Does not raise — the caller
        gets the best frame we could produce.
        """
        if df.empty:
            logger.warning("Combiner: empty frame for {}:{}", symbol, timeframe)
            return

        # Duplicate columns
        if df.columns.duplicated().any():
            dups = df.columns[df.columns.duplicated()].tolist()
            logger.error("Combiner: duplicate columns for {}:{}: {}",
                         symbol, timeframe, dups)

        # Fully-NaN feature columns (skip OHLCV which are always populated)
        ohlcv = {"open", "high", "low", "close", "volume"}
        for col in df.columns:
            if col in ohlcv:
                continue
            if df[col].isna().all():
                logger.warning(
                    "Combiner: column {!r} is entirely NaN for {}:{}",
                    col, symbol, timeframe,
                )

        # Index uniqueness
        if not df.index.is_unique:
            logger.error("Combiner: non-unique index for {}:{}", symbol, timeframe)

        # Index monotonic
        if not df.index.is_monotonic_increasing:
            logger.warning("Combiner: index not monotonic for {}:{}", symbol, timeframe)

    # ------------------------------------------------------------------
    # Caching
    # ------------------------------------------------------------------
    async def _cache(self, df: pd.DataFrame, symbol: str, timeframe: str) -> None:
        """Cache the combined frame to Redis with FEATURE_TTL (300s)."""
        try:
            # Convert to dict-of-lists (columnar) for JSON serialisation
            # Convert Timestamps to ISO strings
            cache_df = df.copy()
            cache_df.index = cache_df.index.astype(str)

            # Replace non-serialisable values (numpy types, NaN)
            cache_df = cache_df.where(pd.notna(cache_df), None)

            payload: dict[str, Any] = {
                "symbol": symbol,
                "timeframe": timeframe,
                "columns": list(df.columns),
                "index": [str(i) for i in df.index],
                "data": cache_df.to_dict(orient="list"),
                "row_count": len(df),
            }
            ok = await cache_features(symbol, payload, feature_name=timeframe)
            if ok:
                logger.info(
                    "Combiner: cached {} rows for {}:{} (TTL={}s)",
                    len(df), symbol, timeframe, FEATURE_TTL,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Cache write failed for {}:{}: {}",
                           symbol, timeframe, exc)


__all__ = ["FeatureCombiner"]
