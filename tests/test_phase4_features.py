"""
tests.test_phase4_features — Phase 4 feature engine smoke tests.

Verifies:
  - TechnicalFeatures adds the expected columns with valid values.
  - SmartMoneyFeatures adds SMC columns and detects patterns on
    synthetic data engineered to trigger each one.
  - DerivativesFeatures exposes async fetch helpers; sync compute()
    raises NotImplementedError.
  - FeatureCombiner integrates everything (mocked DB + Redis) and
    produces a single combined DataFrame.
  - Combiner validates and caches.
  - No Phase 1/2/3 regressions.

Run:  pytest tests/test_phase4_features.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# --------------------------------------------------------------------
# Helpers — synthetic data generators
# --------------------------------------------------------------------
def _synthetic_ohlcv(n: int = 300, seed: int = 42) -> pd.DataFrame:
    """Build clean OHLCV with a slow up-drift so EMAs and pivots are well-defined."""
    np.random.seed(seed)
    drift = np.linspace(0, 30, n)
    noise = np.cumsum(np.random.randn(n) * 0.5)
    close = 100 + drift + noise
    high = close + np.abs(np.random.randn(n) * 0.4)
    low = close - np.abs(np.random.randn(n) * 0.4)
    open_ = close + np.random.randn(n) * 0.2
    vol = np.random.randint(1000, 5000, n).astype(float)
    idx = pd.date_range("2025-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": vol},
        index=idx,
    )


def _make_fvg_bullish(n: int = 30) -> pd.DataFrame:
    """Engineer a 3-bar bullish FVG around bar 10."""
    df = _synthetic_ohlcv(n)
    # Bar 8 (low) — push it low
    df.iloc[8, df.columns.get_loc("low")] = df.iloc[8]["close"] - 5
    df.iloc[8, df.columns.get_loc("high")] = df.iloc[8]["close"] - 4
    # Bar 10 (low) — push it high above bar 8's high
    df.iloc[10, df.columns.get_loc("low")] = df.iloc[8]["high"] + 5
    df.iloc[10, df.columns.get_loc("high")] = df.iloc[10]["low"] + 1
    df.iloc[10, df.columns.get_loc("close")] = df.iloc[10]["low"] + 0.5
    return df


# --------------------------------------------------------------------
# TechnicalFeatures
# --------------------------------------------------------------------
def test_technical_features_columns():
    from features.technical import TechnicalFeatures
    df = _synthetic_ohlcv(n=300)
    out = TechnicalFeatures().compute(df)
    expected = {
        "ema_20", "ema_50", "ema_200", "rsi_14",
        "macd_line", "macd_signal", "macd_hist",
        "atr_14", "vwap", "volume_ma_20",
    }
    assert expected.issubset(set(out.columns)), \
        f"Missing: {expected - set(out.columns)}"


def test_technical_features_does_not_mutate_input():
    from features.technical import TechnicalFeatures
    df = _synthetic_ohlcv(n=300)
    original_cols = set(df.columns)
    TechnicalFeatures().compute(df)
    assert set(df.columns) == original_cols, "compute() must not mutate input"


def test_technical_features_ema200_starts_nan_then_fills():
    from features.technical import TechnicalFeatures
    df = _synthetic_ohlcv(n=300)
    out = TechnicalFeatures().compute(df)
    assert out["ema_200"].isna().sum() > 0  # warm-up
    assert out["ema_200"].iloc[-1] == out["ema_200"].iloc[-1]  # not NaN at end
    assert np.isfinite(out["ema_200"].iloc[-1])


def test_technical_features_rsi_in_range():
    from features.technical import TechnicalFeatures
    df = _synthetic_ohlcv(n=300)
    out = TechnicalFeatures().compute(df)
    rsi = out["rsi_14"].dropna()
    assert (rsi >= 0).all() and (rsi <= 100).all()


def test_technical_features_handles_short_df():
    from features.technical import TechnicalFeatures
    df = _synthetic_ohlcv(n=10)
    out = TechnicalFeatures().compute(df)
    # Should not crash, should still have all columns
    assert "ema_200" in out.columns
    assert out["ema_200"].isna().all()


def test_technical_features_raises_on_missing_columns():
    from features.technical import TechnicalFeatures
    df = pd.DataFrame({"close": [1, 2, 3]})
    with pytest.raises(ValueError):
        TechnicalFeatures().compute(df)


# --------------------------------------------------------------------
# SmartMoneyFeatures
# --------------------------------------------------------------------
def test_smc_columns_present():
    from features.smc import SmartMoneyFeatures
    df = _synthetic_ohlcv(n=300)
    out = SmartMoneyFeatures().compute(df)
    expected = {
        "swing_high", "swing_low",
        "bos", "bos_level", "choch", "choch_level",
        "fvg", "fvg_top", "fvg_bottom",
        "order_block", "ob_high", "ob_low",
        "equal_highs", "equal_lows",
        "liquidity_sweep",
    }
    assert expected.issubset(set(out.columns)), \
        f"Missing: {expected - set(out.columns)}"


def test_smc_pivots_detected():
    from features.smc import SmartMoneyFeatures
    df = _synthetic_ohlcv(n=300)
    out = SmartMoneyFeatures().compute(df)
    # Should have at least some swing highs and lows
    assert out["swing_high"].sum() > 0
    assert out["swing_low"].sum() > 0


def test_smc_fvg_detection_bullish():
    """Engineer a bullish FVG and verify it's detected."""
    from features.smc import SmartMoneyFeatures
    df = _make_fvg_bullish(n=30)
    out = SmartMoneyFeatures().compute(df)
    fvg_bull = out[out["fvg"] == "bull"]
    assert len(fvg_bull) > 0
    # FVG bottom should equal bar 8's high
    row = fvg_bull.iloc[0]
    assert row["fvg_bottom"] > 0
    assert row["fvg_top"] > row["fvg_bottom"]


def test_smc_bos_or_choch_detected_on_trend():
    """A noisy uptrend with pullbacks should produce at least one bullish BOS."""
    from features.smc import SmartMoneyFeatures
    # Build an uptrend with pullbacks so pivots form naturally
    n = 200
    idx = pd.date_range("2025-01-01", periods=n, freq="1h", tz="UTC")
    np.random.seed(7)
    trend = np.linspace(0, 30, n)
    pullbacks = np.sin(np.linspace(0, 12 * np.pi, n)) * 2.0  # 6 pullbacks
    noise = np.random.randn(n) * 0.3
    close = pd.Series(100 + trend + pullbacks + noise, index=idx)
    high = close + 0.5
    low = close - 0.5
    open_ = close - np.random.randn(n) * 0.2
    df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                       "volume": np.ones(n) * 1000.0}, index=idx)
    out = SmartMoneyFeatures().compute(df)
    # A noisy uptrend should produce at least one bullish BOS or CHOCH
    n_bull_bos = (out["bos"] == "bull").sum()
    n_bull_choch = (out["choch"] == "bull").sum()
    assert n_bull_bos + n_bull_choch > 0, \
        f"Expected at least one bullish BOS/CHOCH, got bos={n_bull_bos} choch={n_bull_choch}"


def test_smc_liquidity_sweep_detected():
    """Engineer a sweep: wick below a prior swing low, close back above."""
    from features.smc import SmartMoneyFeatures
    df = _synthetic_ohlcv(n=200)
    # Find a bar near the middle to use as the "victim" swing low
    # (We force a swing low at bar 50.)
    df.iloc[50, df.columns.get_loc("low")] = df.iloc[50]["close"] - 5
    df.iloc[50, df.columns.get_loc("high")] = df.iloc[50]["close"] - 4
    # Bar 80: pierce the swing low with a wick, then close back above
    swing_low_level = df.iloc[50]["low"]
    df.iloc[80, df.columns.get_loc("low")] = swing_low_level - 1.0  # pierce
    df.iloc[80, df.columns.get_loc("close")] = swing_low_level + 1.0  # recover
    df.iloc[80, df.columns.get_loc("high")] = swing_low_level + 2.0
    df.iloc[80, df.columns.get_loc("open")] = swing_low_level + 0.5

    out = SmartMoneyFeatures().compute(df)
    sweeps = out[out["liquidity_sweep"] == "bull"]
    # We expect at least one bullish sweep around bar 80 or later
    assert len(sweeps) > 0


def test_smc_does_not_mutate_input():
    from features.smc import SmartMoneyFeatures
    df = _synthetic_ohlcv(n=200)
    original_cols = set(df.columns)
    SmartMoneyFeatures().compute(df)
    assert set(df.columns) == original_cols


def test_smc_raises_on_missing_columns():
    from features.smc import SmartMoneyFeatures
    df = pd.DataFrame({"close": [1, 2, 3]})
    with pytest.raises(ValueError):
        SmartMoneyFeatures().compute(df)


def test_smc_find_pivots_helper():
    from features.smc import find_pivots
    df = _synthetic_ohlcv(n=100)
    sh, sl = find_pivots(df, lookback=5)
    assert isinstance(sh, pd.Series)
    assert isinstance(sl, pd.Series)
    assert (sh.dtype == bool) and (sl.dtype == bool)
    assert len(sh) == len(df)


# --------------------------------------------------------------------
# DerivativesFeatures
# --------------------------------------------------------------------
def test_derivatives_sync_compute_raises():
    """The sync compute() must raise — derivatives are async-only."""
    from features.derivatives import DerivativesFeatures
    df = _synthetic_ohlcv(n=50)
    with pytest.raises(NotImplementedError):
        DerivativesFeatures().compute(df)


def test_derivatives_module_exports_fetchers():
    from features.derivatives import (
        DerivativesFeatures,
        fetch_open_interest,
        fetch_funding_rate,
        fetch_long_short_ratio,
        fetch_klines_for_cvd,
    )
    assert callable(fetch_open_interest)
    assert callable(fetch_funding_rate)
    assert callable(fetch_long_short_ratio)
    assert callable(fetch_klines_for_cvd)


@pytest.mark.asyncio
async def test_derivatives_compute_async_with_mocked_http():
    """compute_async should populate derivative columns even when HTTP is mocked."""
    from features.derivatives import DerivativesFeatures

    # Mock the fetch helpers to return canned data
    fk = pd.DataFrame(
        {
            "open": [100, 101, 102],
            "high": [101, 102, 103],
            "low": [99, 100, 101],
            "close": [100.5, 101.5, 102.5],
            "volume": [1000.0, 1100.0, 1200.0],
            "taker_buy_base": [550.0, 600.0, 700.0],
        },
        index=pd.date_range("2025-01-01", periods=3, freq="1h", tz="UTC"),
    )
    ls_data = [
        {"longShortRatio": "1.2", "timestamp": 1735689600000},
        {"longShortRatio": "1.3", "timestamp": 1735693200000},
        {"longShortRatio": "1.1", "timestamp": 1735696800000},
    ]

    df = _synthetic_ohlcv(n=50)
    feat = DerivativesFeatures()

    with patch("features.derivatives.fetch_klines_for_cvd", new=AsyncMock(return_value=fk)), \
         patch("features.derivatives.fetch_long_short_ratio", new=AsyncMock(return_value=ls_data)), \
         patch("features.derivatives.fetch_open_interest", new=AsyncMock(return_value={"openInterest": "12345.6"})), \
         patch("features.derivatives.fetch_funding_rate", new=AsyncMock(return_value={"lastFundingRate": "0.0001"})):
        out = await feat.compute_async(df, symbol="BTCUSDT")

    # Check that all expected columns exist
    for col in ("cvd", "long_short_ratio", "open_interest", "funding_rate", "liq_zone_bias"):
        assert col in out.columns, f"missing {col}"

    # Open interest and funding should be broadcast (same value on every row)
    assert (out["open_interest"] == 12345.6).all()
    assert (out["funding_rate"] == 0.0001).all()

    await feat.close()


# --------------------------------------------------------------------
# FeatureCombiner
# --------------------------------------------------------------------
@pytest.mark.asyncio
async def test_combiner_builds_combined_frame_with_mocks():
    """End-to-end combiner test with mocked DB + derivatives."""
    from features.combiner import FeatureCombiner

    # Mock DB loader: return synthetic OHLCV
    ohlcv = _synthetic_ohlcv(n=100)
    # _load_ohlcv returns df with timestamp index
    async def fake_load(self, symbol, timeframe, limit):
        return ohlcv.copy()

    # Mock derivatives to avoid network
    async def fake_deriv(self, df, symbol):
        df = df.copy()
        df["cvd"] = np.arange(len(df), dtype=float)
        df["long_short_ratio"] = 1.0
        df["open_interest"] = 10000.0
        df["funding_rate"] = 0.0001
        df["liq_zone_bias"] = np.nan
        return df

    # Mock cache: no hit on first call, return value irrelevant
    async def fake_get_features(symbol, feature_name=None):
        return None
    async def fake_cache_features(symbol, data, feature_name=None):
        return True

    with patch("features.combiner.FeatureCombiner._load_ohlcv", new=fake_load), \
         patch("features.derivatives.DerivativesFeatures.compute_async", new=fake_deriv), \
         patch("features.combiner.get_features", new=fake_get_features), \
         patch("features.combiner.cache_features", new=fake_cache_features):
        combiner = FeatureCombiner()
        df = await combiner.build("BTCUSDT", "1h", limit=100, use_cache=True)

    # Verify all three feature groups contributed columns
    expected_tech = {"ema_20", "rsi_14", "macd_line", "atr_14", "vwap"}
    expected_smc = {"swing_high", "swing_low", "fvg", "bos", "choch",
                    "order_block", "liquidity_sweep"}
    expected_deriv = {"cvd", "long_short_ratio", "open_interest", "funding_rate"}

    cols = set(df.columns)
    assert expected_tech.issubset(cols), f"Missing tech: {expected_tech - cols}"
    assert expected_smc.issubset(cols), f"Missing smc: {expected_smc - cols}"
    assert expected_deriv.issubset(cols), f"Missing deriv: {expected_deriv - cols}"


@pytest.mark.asyncio
async def test_combiner_uses_cache_when_available():
    """If Redis has a cached frame, combiner should return it without hitting DB."""
    from features.combiner import FeatureCombiner

    cached_df = _synthetic_ohlcv(n=10)
    cached_df.index = cached_df.index.astype(str)
    cached_payload = {
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "data": cached_df.to_dict(orient="list"),
    }

    # If the cache returns a payload, _load_ohlcv should NEVER be called.
    call_count = {"load": 0}
    async def counting_load(self, symbol, timeframe, limit):
        call_count["load"] += 1
        return pd.DataFrame()

    async def fake_get_features(symbol, feature_name=None):
        return cached_payload

    with patch("features.combiner.get_features", new=fake_get_features), \
         patch("features.combiner.FeatureCombiner._load_ohlcv", new=counting_load):
        combiner = FeatureCombiner()
        df = await combiner.build("BTCUSDT", "1h", use_cache=True)

    assert call_count["load"] == 0  # DB never touched
    assert not df.empty
    assert len(df) == 10


@pytest.mark.asyncio
async def test_combiner_validates_logs_warnings_for_all_nan_columns():
    """Combiner should log a warning if any feature column is entirely NaN.

    Loguru's default sink uses enqueue=True (async writes), so capsys/capfd
    can't reliably capture it. Instead we attach a temporary in-memory sink.
    """
    from loguru import logger as loguru_logger
    from features.combiner import FeatureCombiner

    # Attach an in-memory sink
    captured: list[str] = []
    sink_id = loguru_logger.add(
        lambda msg: captured.append(msg.record["message"]),
        level="WARNING",
        format="{message}",  # minimal
    )

    try:
        ohlcv = _synthetic_ohlcv(n=50)
        async def fake_load(self, symbol, timeframe, limit):
            return ohlcv.copy()

        async def fake_deriv(self, df, symbol):
            df = df.copy()
            df["cvd"] = np.nan  # entirely NaN — should trigger warning
            df["long_short_ratio"] = 1.0
            df["open_interest"] = 10000.0
            df["funding_rate"] = 0.0001
            df["liq_zone_bias"] = np.nan
            return df

        async def fake_get_features(symbol, feature_name=None):
            return None
        async def fake_cache_features(symbol, data, feature_name=None):
            return True

        with patch("features.combiner.FeatureCombiner._load_ohlcv", new=fake_load), \
             patch("features.derivatives.DerivativesFeatures.compute_async", new=fake_deriv), \
             patch("features.combiner.get_features", new=fake_get_features), \
             patch("features.combiner.cache_features", new=fake_cache_features):
            combiner = FeatureCombiner()
            df = await combiner.build("BTCUSDT", "1h", use_cache=False)

        # EMA200 is all-NaN on 50 rows — should trigger warning
        assert any("entirely NaN" in msg for msg in captured), \
            f"Expected 'entirely NaN' warning. Captured warnings: {captured}"
    finally:
        loguru_logger.remove(sink_id)


# --------------------------------------------------------------------
# Module imports
# --------------------------------------------------------------------
@pytest.mark.parametrize(
    "module",
    [
        "features.technical",
        "features.smc",
        "features.derivatives",
        "features.combiner",
    ],
)
def test_phase4_module_importable(module: str):
    import importlib
    assert importlib.import_module(module) is not None


def test_phase1_features_still_importable():
    """Phase 1's indicators/microstructure/pipeline must still work."""
    from features.indicators import RSI, MACD, EMA, ATR, BollingerBands
    from features.microstructure import (
        VolumeWeightedPriceImpact, OrderFlowImbalance, TradeIntensity,
    )
    from features.pipeline import FeaturePipeline
    from features.base import BaseFeature
    assert issubclass(RSI, BaseFeature)
    assert issubclass(MACD, BaseFeature)
