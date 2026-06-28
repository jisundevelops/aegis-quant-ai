"""
data.crypto_fetcher — Multi-source crypto data fetcher.

Tries multiple data sources in order until one succeeds:
  1. Binance API (fastest, but geo-blocked in US)
  2. Yahoo Finance (slower, but always works — not geo-restricted)

This solves the "Service unavailable from a restricted location" error
that occurs when Binance blocks Render's US-based IP address.
"""
from __future__ import annotations

import asyncio
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

# --------------------------------------------------------------------
# Symbol mapping: Binance symbol → Yahoo Finance symbol
# --------------------------------------------------------------------
_BINANCE_TO_YAHOO: dict[str, str] = {
    "BTCUSDT": "BTC-USD",
    "ETHUSDT": "ETH-USD",
    "BNBUSDT": "BNB-USD",
    "SOLUSDT": "SOL-USD",
    "XRPUSDT": "XRP-USD",
    "ADAUSDT": "ADA-USD",
    "DOGEUSDT": "DOGE-USD",
    "AVAXUSDT": "AVAX-USD",
}

# Yahoo interval mapping
_YF_INTERVAL_MAP: dict[str, str] = {
    "15m": "15m",
    "1h": "60m",
    "4h": "60m",  # Yahoo doesn't have 4h, use 60m and we'll resample
    "1d": "1d",
}


async def fetch_crypto_ohlcv(
    symbol: str,
    timeframe: str,
    limit: int = 500,
) -> pd.DataFrame:
    """Fetch crypto OHLCV data, trying Binance first then Yahoo.

    Parameters
    ----------
    symbol    : Binance-style symbol (e.g. "BTCUSDT")
    timeframe : "15m" | "1h" | "4h" | "1d"
    limit     : number of bars (max 1000 for Binance)

    Returns
    -------
    DataFrame with columns: open, high, low, close, volume (tz-aware UTC index)
    """
    # Cap at 1000 (Binance limit)
    limit = min(limit, 1000)

    # Try Binance first
    try:
        from data.binance import BinanceConnector
        bc = BinanceConnector()
        try:
            df = await bc.fetch_ohlcv(symbol, timeframe, limit=limit)
            if not df.empty:
                logger.info("Crypto data from Binance: {} bars for {} {}",
                            len(df), symbol, timeframe)
                return df
        finally:
            await bc.close()
    except Exception as exc:
        logger.warning("Binance fetch failed for {} {}: {}", symbol, timeframe, exc)

    # Fallback to Yahoo Finance
    yf_symbol = _BINANCE_TO_YAHOO.get(symbol, symbol.replace("USDT", "-USD"))
    yf_interval = _YF_INTERVAL_MAP.get(timeframe, "60m")

    logger.info("Falling back to Yahoo Finance: {} → {} (interval={})",
                symbol, yf_symbol, yf_interval)

    df = await asyncio.to_thread(_fetch_yahoo_sync, yf_symbol, yf_interval, limit)

    if df.empty:
        raise ValueError(f"No data from Binance or Yahoo for {symbol} {timeframe}")

    # If timeframe is 4h, resample from 1h
    if timeframe == "4h" and yf_interval == "60m":
        df = _resample_to_4h(df)

    logger.info("Crypto data from Yahoo: {} bars for {} {}",
                len(df), symbol, timeframe)
    return df


def _fetch_yahoo_sync(symbol: str, interval: str, limit: int) -> pd.DataFrame:
    """Sync yfinance call — must run in threadpool."""
    import yfinance as yf

    # Determine period based on interval
    period_map = {
        "15m": "60d",   # Yahoo max for 15m
        "60m": "730d",  # Yahoo max for 1h
        "1d": "max",
    }
    period = period_map.get(interval, "60d")

    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(
            period=period,
            interval=interval,
            auto_adjust=False,
            repair=True,
            actions=False,
        )
    except Exception as exc:
        logger.error("Yahoo fetch failed for {}: {}", symbol, exc)
        return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()

    # Normalize columns
    df = df.rename(columns=str.lower)
    needed = ["open", "high", "low", "close", "volume"]
    for col in needed:
        if col not in df.columns:
            df[col] = float("nan")
    df = df[needed]

    # Coerce index to UTC
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    df.index.name = "timestamp"

    # Drop NaN rows
    df = df.dropna(subset=["open", "high", "low", "close"])
    if df.empty:
        return pd.DataFrame()

    # Tail-trim
    if limit and len(df) > limit:
        df = df.iloc[-limit:]

    return df


def _resample_to_4h(df: pd.DataFrame) -> pd.DataFrame:
    """Resample 1h data to 4h bars."""
    resampled = df.resample("4h", label="left", closed="left").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna()
    return resampled


async def build_features_from_crypto(
    symbol: str,
    timeframe: str,
    limit: int = 500,
) -> pd.DataFrame:
    """Fetch crypto data + build full feature set (no DB required).

    This is the ultimate fallback — works even if:
    - Database is down/paused/empty
    - Binance is geo-blocked (US servers)
    - Only Yahoo Finance is available

    Returns a DataFrame with all Phase 4 feature columns.
    """
    from features.technical import TechnicalFeatures
    from features.smc import SmartMoneyFeatures

    # 1. Fetch OHLCV
    df = await fetch_crypto_ohlcv(symbol, timeframe, limit=limit)
    if df.empty:
        raise ValueError(f"No data available for {symbol} {timeframe}")

    # 2. Build technical features
    df = TechnicalFeatures().compute(df)

    # 3. Build SMC features
    df = SmartMoneyFeatures().compute(df)

    # 4. Add mock derivatives columns (real ones need Binance Futures API)
    df["open_interest"] = 1_000_000_000.0
    df["funding_rate"] = 0.0001
    df["long_short_ratio"] = 1.2
    df["cvd"] = np.cumsum(np.random.randn(len(df)) * 100)
    df["liq_zone_bias"] = None

    logger.info("Built {} feature rows for {} {} (crypto fetcher)",
                len(df), symbol, timeframe)
    return df


__all__ = ["fetch_crypto_ohlcv", "build_features_from_crypto"]
