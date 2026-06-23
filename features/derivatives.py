"""
features.derivatives — Binance Futures derivatives data features.

Fetches public derivatives metrics from the Binance USDⓈ-M Futures API
(no API key required for the public endpoints used here):

  - Open Interest          (fapi/v1/openInterest)
  - Funding Rate           (fapi/v1/premiumIndex)
  - Long/Short Ratio       (futures/data/globalLongShortAccountRatio)
  - CVD (Cumulative Volume Delta)
      - Approximated from klines' taker buy base volume vs total volume.
        Binance klines expose `taker_buy_base_asset_volume` (aggressive
        buys) — CVD = cumsum(taker_buy - (volume - taker_buy)).
  - Liquidation zone estimate
      - Derived from large OI changes (Δ OI beyond 1.5σ) plus the
        close direction — gives a directional bias for liquidation
        cascades.

All fetches are async and use `httpx.AsyncClient`. Results are merged
onto the OHLCV DataFrame indexed by timestamp.

Binance Futures symbols typically mirror spot (BTCUSDT, ETHUSDT).
"""
from __future__ import annotations

import asyncio
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

from config import settings
from features.base import BaseFeature

# --------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------
_FAPI_BASE = "https://fapi.binance.com"
_FAPI_TESTNET_BASE = "https://testnet.binancefuture.com"

# Period strings accepted by Binance for long/short ratio + OI history
_LS_PERIOD_MAP: dict[str, str] = {
    "15m": "15m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
}

# --------------------------------------------------------------------
# Module-level HTTP client (lazy)
# --------------------------------------------------------------------
_http_client: Any = None


async def _get_http() -> Any:
    """Lazy singleton httpx.AsyncClient."""
    global _http_client
    if _http_client is None:
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover
            raise ImportError("httpx is required: pip install httpx") from exc
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0),
            headers={"User-Agent": settings.yfinance_user_agent},
        )
    return _http_client


async def _close_http() -> None:
    global _http_client
    if _http_client is not None:
        try:
            await _http_client.aclose()
        except Exception:  # noqa: BLE001
            pass
        _http_client = None


# --------------------------------------------------------------------
# Public fetch helpers (one per metric)
# --------------------------------------------------------------------
async def fetch_open_interest(symbol: str) -> dict | None:
    """Current open interest (notional in USDT)."""
    http = await _get_http()
    base = _FAPI_TESTNET_BASE if settings.binance_testnet else _FAPI_BASE
    r = await http.get(f"{base}/fapi/v1/openInterest", params={"symbol": symbol})
    if r.status_code != 200:
        logger.warning("OI fetch failed for {}: HTTP {}", symbol, r.status_code)
        return None
    return r.json()  # {"openInterest": "...", "symbol": "...", "time": ...}


async def fetch_funding_rate(symbol: str) -> dict | None:
    """Current funding rate + mark price."""
    http = await _get_http()
    base = _FAPI_TESTNET_BASE if settings.binance_testnet else _FAPI_BASE
    r = await http.get(f"{base}/fapi/v1/premiumIndex", params={"symbol": symbol})
    if r.status_code != 200:
        logger.warning("Funding fetch failed for {}: HTTP {}", symbol, r.status_code)
        return None
    return r.json()  # {"symbol","markPrice","indexPrice","lastFundingRate","nextFundingTime","time"}


async def fetch_long_short_ratio(
    symbol: str, period: str = "1h", limit: int = 30
) -> list[dict] | None:
    """Historical long/short account ratio."""
    http = await _get_http()
    base = _FAPI_TESTNET_BASE if settings.binance_testnet else _FAPI_BASE
    r = await http.get(
        f"{base}/futures/data/globalLongShortAccountRatio",
        params={"symbol": symbol, "period": period, "limit": limit},
    )
    if r.status_code != 200:
        logger.warning("L/S fetch failed for {}: HTTP {}", symbol, r.status_code)
        return None
    return r.json()  # list of {"symbol","longShortRatio","longAccount","shortAccount","timestamp"}


async def fetch_klines_for_cvd(
    symbol: str, interval: str = "1h", limit: int = 500
) -> pd.DataFrame | None:
    """Fetch USDⓈ-M futures klines for CVD computation.

    Binance futures klines return 12 columns; the 9th column is
    `taker_buy_base_asset_volume` (aggressive-buy volume).
    """
    http = await _get_http()
    base = _FAPI_TESTNET_BASE if settings.binance_testnet else _FAPI_BASE
    r = await http.get(
        f"{base}/fapi/v1/klines",
        params={"symbol": symbol, "interval": interval, "limit": limit},
    )
    if r.status_code != 200:
        logger.warning("Futures klines fetch failed for {}: HTTP {}", symbol, r.status_code)
        return None
    raw = r.json()
    if not raw:
        return None
    df = pd.DataFrame(
        raw,
        columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "taker_buy_base",
            "taker_buy_quote", "ignore1", "ignore2",
        ],
    )
    for col in ("open", "high", "low", "close", "volume", "taker_buy_base"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    return df.set_index("timestamp")[["open", "high", "low", "close", "volume", "taker_buy_base"]]


# --------------------------------------------------------------------
# Feature class
# --------------------------------------------------------------------
class DerivativesFeatures(BaseFeature):
    """Fetch derivatives metrics and compute CVD + liquidation-zone estimate."""

    name = "derivatives"

    def __init__(self, interval: str = "1h", ls_period: str | None = None) -> None:
        self.interval = interval
        self.ls_period = ls_period or _LS_PERIOD_MAP.get(interval, "1h")

    # ------------------------------------------------------------------
    # Public API (BaseFeature contract — operates on a DataFrame)
    # ------------------------------------------------------------------
    async def compute_async(self, df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """Asynchronously fetch derivatives metrics and merge onto df.

        This is async because it hits the network. The synchronous
        `compute()` (required by BaseFeature) raises — callers must use
        `compute_async()` for this feature.
        """
        if df is None or df.empty:
            return df.copy() if df is not None else df
        if "close" not in df.columns:
            raise ValueError("DerivativesFeatures requires a 'close' column")

        out = df.copy()
        # Initialise columns. Numeric metrics are float NaN; the
        # liq_zone_bias label column must be object dtype for strings.
        out["open_interest"] = np.nan
        out["funding_rate"] = np.nan
        out["long_short_ratio"] = np.nan
        out["cvd"] = np.nan
        out["liq_zone_bias"] = pd.Series([np.nan] * len(out), index=out.index, dtype="object")

        # ---------- CVD (from futures klines, aligned by timestamp) ----------
        try:
            fk = await fetch_klines_for_cvd(symbol, interval=self.interval, limit=len(out))
            if fk is not None and not fk.empty:
                # Compute CVD: aggressive buy - aggressive sell
                taker_buy = fk["taker_buy_base"]
                taker_sell = fk["volume"] - taker_buy
                delta = taker_buy - taker_sell
                fk["cvd"] = delta.cumsum()
                # Merge onto `out` by nearest timestamp
                out = out.join(fk[["cvd"]], how="left")
                # If the join produced a duplicate cvd column, normalise
                if "cvd" in out.columns:
                    out["cvd"] = out["cvd"].ffill()
        except Exception as exc:  # noqa: BLE001
            logger.warning("CVD computation failed for {}: {}", symbol, exc)

        # ---------- Long/Short Ratio (historical) ----------
        try:
            ls = await fetch_long_short_ratio(symbol, period=self.ls_period, limit=30)
            if ls:
                ls_df = pd.DataFrame(ls)
                ls_df["timestamp"] = pd.to_datetime(
                    ls_df["timestamp"].astype("int64"), unit="ms", utc=True
                )
                ls_df = ls_df.set_index("timestamp")
                ls_df["longShortRatio"] = pd.to_numeric(
                    ls_df["longShortRatio"], errors="coerce"
                )
                # Join raw ratio then forward-fill into our canonical column
                out = out.join(ls_df[["longShortRatio"]], how="left")
                out["long_short_ratio"] = out["longShortRatio"].ffill()
                # Drop the raw column to keep schema clean
                out = out.drop(columns=["longShortRatio"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("L/S merge failed for {}: {}", symbol, exc)

        # ---------- Latest Open Interest + Funding (broadcast) ----------
        try:
            oi = await fetch_open_interest(symbol)
            if oi and "openInterest" in oi:
                out["open_interest"] = float(oi["openInterest"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("OI merge failed for {}: {}", symbol, exc)

        try:
            fr = await fetch_funding_rate(symbol)
            if fr and "lastFundingRate" in fr:
                out["funding_rate"] = float(fr["lastFundingRate"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("Funding merge failed for {}: {}", symbol, exc)

        # ---------- Liquidation zone estimate (from OI delta proxy) ----------
        # Without OI history, we proxy liquidation pressure from large
        # CVD jumps combined with directional close moves.
        self._estimate_liq_zones(out)

        return out

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:  # type: ignore[override]
        """Sync BaseFeature contract — NOT supported for derivatives.

        Use `compute_async()` instead. The derivatives feature requires
        network access and cannot run synchronously.
        """
        raise NotImplementedError(
            "DerivativesFeatures is async-only. Call await instance.compute_async(df, symbol=...)"
        )

    # ------------------------------------------------------------------
    # Liquidation-zone estimator
    # ------------------------------------------------------------------
    def _estimate_liq_zones(self, df: pd.DataFrame) -> None:
        """Flag bars where liquidation cascades likely occurred.

        Heuristic:
          1. Compute the rolling 20-bar std of CVD deltas.
          2. A bar is a "long liq zone" if delta < -1.5σ AND close < open
             (price dropping on aggressive selling — longs getting stopped).
          3. Symmetric for "short liq zone".
        """
        if "cvd" not in df.columns or df["cvd"].isna().all():
            return
        delta = df["cvd"].diff()
        rolling_std = delta.rolling(20, min_periods=5).std()
        threshold = 1.5 * rolling_std

        # Long liquidation: aggressive selling spike + down candle
        long_liq = (delta < -threshold) & (df["close"] < df["open"])
        # Short liquidation: aggressive buying spike + up candle
        short_liq = (delta > threshold) & (df["close"] > df["open"])

        df.loc[long_liq, "liq_zone_bias"] = "long"
        df.loc[short_liq, "liq_zone_bias"] = "short"

    # ------------------------------------------------------------------
    async def close(self) -> None:
        await _close_http()


__all__ = [
    "DerivativesFeatures",
    "fetch_open_interest",
    "fetch_funding_rate",
    "fetch_long_short_ratio",
    "fetch_klines_for_cvd",
]
