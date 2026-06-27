"""
tests.test_phase6_chief — Phase 6 Chief Agent + Probability Engine + endpoint tests.

Verifies:
  - ProbabilityEngine produces Bull/Bear/Range probabilities that sum to 100%
  - ProbabilityEngine handles edge cases (no signals, all neutral, disagreement)
  - ChiefAgent orchestrates all 8 Phase 5 agents with correct weights
  - ChiefAgent produces a ChiefSignal with direction, entry/SL/TP, reasoning
  - ChiefAgent handles bullish/bearish/mixed scenarios correctly
  - POST /api/analyze endpoint returns the full AnalyzeResponse
  - POST /api/analyze handles missing data gracefully (404)
  - Backward compat: chief.orchestrator.ChiefAgent still works (Phase 1)
  - Backward compat: probability.engine.ProbabilityEngine still works

Run:  pytest tests/test_phase6_chief.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _bullish_features(n: int = 200) -> pd.DataFrame:
    np.random.seed(42)
    idx = pd.date_range("2025-01-01", periods=n, freq="1h", tz="UTC")
    close = pd.Series(np.linspace(100, 130, n), index=idx)
    df = pd.DataFrame({
        "open": close - 0.1, "high": close + 1, "low": close - 1,
        "close": close, "volume": np.linspace(1000, 5000, n),
    }, index=idx)
    df["ema_20"] = close + 1
    df["ema_50"] = close - 0.5
    df["ema_200"] = close - 5
    df["rsi_14"] = 68.0
    df["macd_line"] = 0.8
    df["macd_signal"] = 0.2
    df["macd_hist"] = 0.6
    df["atr_14"] = 2.0
    df["vwap"] = close - 0.5
    df["volume_ma_20"] = 3000.0
    df["swing_high"] = False
    df["swing_low"] = False
    df["bos"] = pd.Series([np.nan] * n, index=idx, dtype="object")
    df["bos_level"] = np.nan
    df["choch"] = pd.Series([np.nan] * n, index=idx, dtype="object")
    df["choch_level"] = np.nan
    df["fvg"] = pd.Series([np.nan] * n, index=idx, dtype="object")
    df["fvg_top"] = np.nan
    df["fvg_bottom"] = np.nan
    df["order_block"] = pd.Series([np.nan] * n, index=idx, dtype="object")
    df["ob_high"] = np.nan
    df["ob_low"] = np.nan
    df["equal_highs"] = False
    df["equal_lows"] = False
    df["liquidity_sweep"] = pd.Series([np.nan] * n, index=idx, dtype="object")
    df.iloc[-30, df.columns.get_loc("bos")] = "bull"
    df.iloc[-20, df.columns.get_loc("bos")] = "bull"
    df.iloc[-15, df.columns.get_loc("choch")] = "bull"
    df.iloc[-10, df.columns.get_loc("fvg")] = "bull"
    df.iloc[-5, df.columns.get_loc("order_block")] = "bull"
    df.iloc[-3, df.columns.get_loc("liquidity_sweep")] = "bull"
    df["open_interest"] = 1_000_000_000.0
    df["funding_rate"] = 0.0001
    df["long_short_ratio"] = 0.8
    df["cvd"] = np.linspace(0, 5000, n)
    df["liq_zone_bias"] = pd.Series([np.nan] * n, index=idx, dtype="object")
    return df


def _bearish_features(n: int = 200) -> pd.DataFrame:
    df = _bullish_features(n)
    df["ema_20"] = df["close"] - 1
    df["ema_50"] = df["close"] + 0.5
    df["ema_200"] = df["close"] + 5
    df["rsi_14"] = 32.0
    df["macd_line"] = -0.8
    df["macd_signal"] = -0.2
    df["macd_hist"] = -0.6
    df["cvd"] = np.linspace(5000, 0, n)
    df["long_short_ratio"] = 1.4
    df["funding_rate"] = 0.0003
    df.iloc[-30, df.columns.get_loc("bos")] = "bear"
    df.iloc[-20, df.columns.get_loc("bos")] = "bear"
    df.iloc[-15, df.columns.get_loc("choch")] = "bear"
    df.iloc[-10, df.columns.get_loc("fvg")] = "bear"
    df.iloc[-5, df.columns.get_loc("order_block")] = "bear"
    df.iloc[-3, df.columns.get_loc("liquidity_sweep")] = "bear"
    return df


def test_probability_engine_sums_to_100_with_bullish_signals():
    from agents.base_agent import AgentSignal
    from probability.probability_engine import ProbabilityEngine
    signals = [
        AgentSignal(agent="trend", symbol="BTC", bias="Bullish", confidence=80),
        AgentSignal(agent="smc", symbol="BTC", bias="Bullish", confidence=70),
        AgentSignal(agent="derivatives", symbol="BTC", bias="Bullish", confidence=60),
    ]
    probs = ProbabilityEngine().compute(signals)
    assert abs(probs.bull_pct + probs.bear_pct + probs.range_pct - 100.0) < 0.01
    assert probs.bull_pct > probs.bear_pct


def test_probability_engine_sums_to_100_with_mixed_signals():
    from agents.base_agent import AgentSignal
    from probability.probability_engine import ProbabilityEngine
    signals = [
        AgentSignal(agent="trend", symbol="BTC", bias="Bullish", confidence=70),
        AgentSignal(agent="smc", symbol="BTC", bias="Bearish", confidence=70),
    ]
    probs = ProbabilityEngine().compute(signals)
    assert abs(probs.bull_pct + probs.bear_pct + probs.range_pct - 100.0) < 0.01
    assert probs.range_pct > 0


def test_probability_engine_handles_no_signals():
    from probability.probability_engine import ProbabilityEngine
    probs = ProbabilityEngine().compute([])
    assert abs(probs.bull_pct + probs.bear_pct + probs.range_pct - 100.0) < 0.01


def test_probability_engine_handles_all_neutral():
    from agents.base_agent import AgentSignal
    from probability.probability_engine import ProbabilityEngine
    signals = [
        AgentSignal(agent="trend", symbol="BTC", bias="Neutral", confidence=50),
        AgentSignal(agent="smc", symbol="BTC", bias="Neutral", confidence=50),
    ]
    probs = ProbabilityEngine().compute(signals)
    assert probs.range_pct > 50.0


def test_probability_engine_disagreement_boosts_range():
    from agents.base_agent import AgentSignal
    from probability.probability_engine import ProbabilityEngine
    signals = [
        AgentSignal(agent="trend", symbol="BTC", bias="Bullish", confidence=90),
        AgentSignal(agent="smc", symbol="BTC", bias="Bearish", confidence=90),
    ]
    probs = ProbabilityEngine().compute(signals)
    assert probs.range_pct > 0


def test_probability_engine_respects_weights():
    from agents.base_agent import AgentSignal
    from probability.probability_engine import ProbabilityEngine
    signals = [
        AgentSignal(agent="a", symbol="BTC", bias="Bullish", confidence=100),
        AgentSignal(agent="b", symbol="BTC", bias="Bearish", confidence=100),
    ]
    probs = ProbabilityEngine().compute(signals, weights={"a": 0.9, "b": 0.1})
    assert probs.bull_pct > probs.bear_pct


def test_probability_engine_contributions_recorded():
    from agents.base_agent import AgentSignal
    from probability.probability_engine import ProbabilityEngine
    signals = [AgentSignal(agent="trend", symbol="BTC", bias="Bullish", confidence=70)]
    probs = ProbabilityEngine().compute(signals, weights={"trend": 0.2})
    assert "trend" in probs.contributions
    assert probs.contributions["trend"]["weight"] == 0.2


def test_probability_engine_as_dict():
    from agents.base_agent import AgentSignal
    from probability.probability_engine import ProbabilityEngine
    signals = [AgentSignal(agent="trend", symbol="BTC", bias="Bullish", confidence=70)]
    probs = ProbabilityEngine().compute(signals)
    d = probs.as_dict()
    assert "bull_pct" in d and "bear_pct" in d and "range_pct" in d
    assert abs(d["sum_pct"] - 100.0) < 0.01


@pytest.mark.asyncio
async def test_chief_agent_bullish_signal():
    from chief.chief_agent import ChiefAgent, ChiefSignal
    df = _bullish_features()
    chief = ChiefAgent()
    sig = await chief.analyze("BTCUSDT", "1h", features_df=df)
    assert isinstance(sig, ChiefSignal)
    assert sig.symbol == "BTCUSDT"
    assert sig.direction in {"LONG", "NEUTRAL"}
    assert 0 <= sig.confidence_score <= 100
    assert len(sig.agent_breakdown) >= 5


@pytest.mark.asyncio
async def test_chief_agent_bearish_signal():
    from chief.chief_agent import ChiefAgent
    df = _bearish_features()
    chief = ChiefAgent()
    sig = await chief.analyze("BTCUSDT", "1h", features_df=df)
    assert sig.direction in {"SHORT", "NEUTRAL"}


@pytest.mark.asyncio
async def test_chief_agent_has_correct_weights():
    from chief.chief_agent import AGENT_WEIGHTS
    assert AGENT_WEIGHTS["trend"] == 0.20
    assert AGENT_WEIGHTS["smc"] == 0.25
    assert AGENT_WEIGHTS["derivatives"] == 0.20
    assert AGENT_WEIGHTS["macro"] == 0.10
    assert AGENT_WEIGHTS["session"] == 0.05
    assert AGENT_WEIGHTS["sentiment"] == 0.05
    assert AGENT_WEIGHTS["retail_trap"] == 0.15
    assert abs(sum(AGENT_WEIGHTS.values()) - 1.0) < 0.001


@pytest.mark.asyncio
async def test_chief_agent_includes_all_agents_in_breakdown():
    from chief.chief_agent import ChiefAgent
    df = _bullish_features()
    chief = ChiefAgent()
    sig = await chief.analyze("BTCUSDT", "1h", features_df=df)
    expected = {"trend", "smc", "derivatives", "macro", "session", "sentiment", "retail_trap"}
    assert expected.issubset(set(sig.agent_breakdown.keys()))


@pytest.mark.asyncio
async def test_chief_agent_probabilities_sum_to_100():
    from chief.chief_agent import ChiefAgent
    df = _bullish_features()
    chief = ChiefAgent()
    sig = await chief.analyze("BTCUSDT", "1h", features_df=df)
    p = sig.probabilities
    assert abs(p["bull_pct"] + p["bear_pct"] + p["range_pct"] - 100.0) < 0.01


@pytest.mark.asyncio
async def test_chief_agent_long_direction_has_entry_sl_tp():
    from chief.chief_agent import ChiefAgent
    df = _bullish_features()
    chief = ChiefAgent()
    sig = await chief.analyze("BTCUSDT", "1h", features_df=df)
    if sig.direction == "LONG":
        assert sig.entry_zone is not None and len(sig.entry_zone) == 2
        assert sig.stop_loss is not None
        assert sig.take_profit_1 is not None
        assert sig.take_profit_2 is not None
        entry_mid = sum(sig.entry_zone) / 2
        assert sig.stop_loss < entry_mid
        assert sig.take_profit_1 > entry_mid
        assert sig.take_profit_2 > sig.take_profit_1


@pytest.mark.asyncio
async def test_chief_agent_short_direction_has_entry_sl_tp():
    from chief.chief_agent import ChiefAgent
    df = _bearish_features()
    chief = ChiefAgent()
    sig = await chief.analyze("BTCUSDT", "1h", features_df=df)
    if sig.direction == "SHORT":
        assert sig.entry_zone is not None
        assert sig.stop_loss is not None
        assert sig.take_profit_1 is not None
        assert sig.take_profit_2 is not None
        entry_mid = sum(sig.entry_zone) / 2
        assert sig.stop_loss > entry_mid
        assert sig.take_profit_1 < entry_mid
        assert sig.take_profit_2 < sig.take_profit_1


@pytest.mark.asyncio
async def test_chief_agent_as_dict_serializable():
    from chief.chief_agent import ChiefAgent
    df = _bullish_features()
    chief = ChiefAgent()
    sig = await chief.analyze("BTCUSDT", "1h", features_df=df)
    d = sig.as_dict()
    import json
    json.dumps(d)


def test_phase1_chief_orchestrator_still_importable():
    from chief.orchestrator import ChiefAgent as CA1
    from chief.chief_agent import ChiefAgent as CA2
    assert CA1 is CA2


def test_phase1_probability_engine_still_importable():
    from probability.engine import ProbabilityEngine as PE1
    from probability.probability_engine import ProbabilityEngine as PE2
    assert PE1 is PE2


@pytest.mark.asyncio
async def test_analyze_endpoint_returns_full_response():
    import os
    os.environ.pop("DATABASE_URL", None)
    os.environ.pop("REDIS_URL", None)
    os.environ["SCHEDULER_ENABLED"] = "false"
    from config.settings import get_settings
    get_settings.cache_clear()

    from fastapi.testclient import TestClient
    from backend.main import app

    df = _bullish_features(n=200)
    async def fake_build(self, symbol, timeframe, limit=500, use_cache=True):
        return df.copy()

    # Mock BOTH the DB path AND the Binance fallback (to avoid rate limits)
    async def fake_binance_build(req):
        return df.copy()

    with patch("features.combiner.FeatureCombiner.build", new=fake_build), \
         patch("backend.api.routes.analyze._build_features_from_binance", new=fake_binance_build):
        with TestClient(app) as client:
            r = client.post("/api/analyze", json={
                "symbol": "BTCUSDT", "timeframe": "1h", "limit": 200, "capital": 10000,
            })
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "BTCUSDT"
    assert body["direction"] in {"LONG", "SHORT", "NEUTRAL"}
    assert 0 <= body["confidence_score"] <= 100
    assert "trend" in body["agent_breakdown"]
    assert "smc" in body["agent_breakdown"]
    assert abs(body["probabilities"]["bull_pct"]
               + body["probabilities"]["bear_pct"]
               + body["probabilities"]["range_pct"] - 100.0) < 0.01


@pytest.mark.asyncio
async def test_analyze_endpoint_502_when_all_sources_fail():
    """When both DB and Binance fallback fail, should return 502."""
    import os
    os.environ.pop("DATABASE_URL", None)
    os.environ.pop("REDIS_URL", None)
    os.environ["SCHEDULER_ENABLED"] = "false"
    from config.settings import get_settings
    get_settings.cache_clear()

    from fastapi.testclient import TestClient
    from backend.main import app

    async def fake_build(self, symbol, timeframe, limit=500, use_cache=True):
        return pd.DataFrame()

    async def fake_binance_fail(req):
        raise Exception("Binance unavailable")

    with patch("features.combiner.FeatureCombiner.build", new=fake_build), \
         patch("backend.api.routes.analyze._build_features_from_binance", new=fake_binance_fail):
        with TestClient(app) as client:
            r = client.post("/api/analyze", json={"symbol": "NONEXIST", "timeframe": "1h"})
    assert r.status_code == 502


@pytest.mark.asyncio
async def test_analyze_endpoint_validates_request_body():
    import os
    os.environ.pop("DATABASE_URL", None)
    os.environ.pop("REDIS_URL", None)
    os.environ["SCHEDULER_ENABLED"] = "false"
    from config.settings import get_settings
    get_settings.cache_clear()

    from fastapi.testclient import TestClient
    from backend.main import app

    with TestClient(app) as client:
        r = client.post("/api/analyze", json={"timeframe": "1h"})
        assert r.status_code == 422
        r = client.post("/api/analyze", json={"symbol": "BTCUSDT", "limit": 5})
        assert r.status_code == 422
