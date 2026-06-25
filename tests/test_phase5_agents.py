"""
tests.test_phase5_agents — Phase 5 agent system smoke tests.

Verifies every Phase 5 agent:
  - Inherits from BaseAgent
  - Returns the correct output type (AgentSignal or subclass)
  - Produces the correct bias/confidence/reasoning contract
  - Handles edge cases (empty df, missing columns, NaN values)

Run:  pytest tests/test_phase5_agents.py -v
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# --------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------
def _feature_df(n: int = 200, seed: int = 42) -> pd.DataFrame:
    """Build a Phase 4-style feature DataFrame with all expected columns."""
    np.random.seed(seed)
    idx = pd.date_range("2025-01-01", periods=n, freq="1h", tz="UTC")
    drift = np.linspace(0, 20, n)
    noise = np.cumsum(np.random.randn(n) * 0.5)
    close = pd.Series(100 + drift + noise, index=idx, name="close")
    high = pd.Series(close.values + 0.5, index=idx)
    low = pd.Series(close.values - 0.5, index=idx)
    open_ = pd.Series(close.values - 0.1, index=idx)
    vol = pd.Series(np.random.randint(1000, 5000, n).astype(float), index=idx)

    df = pd.DataFrame({
        "open": open_, "high": high, "low": low, "close": close, "volume": vol,
    }, index=idx)

    # Technical features (canonical Phase 4 columns)
    df["ema_20"] = close.rolling(20, min_periods=1).mean()
    df["ema_50"] = close.rolling(50, min_periods=1).mean()
    df["ema_200"] = close.rolling(200, min_periods=1).mean()
    df["rsi_14"] = pd.Series(50.0 + np.random.randn(n) * 10, index=idx)
    df["macd_line"] = df["ema_20"] - df["ema_50"]
    df["macd_signal"] = df["macd_line"].rolling(9, min_periods=1).mean()
    df["macd_hist"] = df["macd_line"] - df["macd_signal"]
    df["atr_14"] = (high - low).rolling(14, min_periods=1).mean()
    df["vwap"] = ((high + low + close) / 3 * vol).rolling(20, min_periods=1).sum() / \
                  vol.rolling(20, min_periods=1).sum()
    df["volume_ma_20"] = vol.rolling(20, min_periods=1).mean()

    # SMC columns (object dtype for labels)
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

    # Derivatives columns
    df["open_interest"] = 1_000_000_000.0
    df["funding_rate"] = 0.0001
    df["long_short_ratio"] = 1.2
    df["cvd"] = np.cumsum(np.random.randn(n) * 100)
    df["liq_zone_bias"] = pd.Series([np.nan] * n, index=idx, dtype="object")

    return df


def _bullish_feature_df(n: int = 200) -> pd.DataFrame:
    """Feature frame engineered to look strongly bullish."""
    df = _feature_df(n)
    # Stack EMAs bullish
    df["ema_20"] = df["close"] + 1.0
    df["ema_50"] = df["close"] - 0.5
    df["ema_200"] = df["close"] - 2.0
    # MACD bullish
    df["macd_line"] = 0.5
    df["macd_signal"] = 0.0
    df["macd_hist"] = 0.5
    # RSI bullish
    df["rsi_14"] = 65.0
    # SMC bullish signals in last 50 bars
    df.iloc[-30, df.columns.get_loc("bos")] = "bull"
    df.iloc[-20, df.columns.get_loc("bos")] = "bull"
    df.iloc[-10, df.columns.get_loc("fvg")] = "bull"
    df.iloc[-5, df.columns.get_loc("order_block")] = "bull"
    df.iloc[-3, df.columns.get_loc("liquidity_sweep")] = "bull"
    df.iloc[-15, df.columns.get_loc("choch")] = "bull"
    return df


def _bearish_feature_df(n: int = 200) -> pd.DataFrame:
    """Feature frame engineered to look strongly bearish."""
    df = _feature_df(n)
    df["ema_20"] = df["close"] - 1.0
    df["ema_50"] = df["close"] + 0.5
    df["ema_200"] = df["close"] + 2.0
    df["macd_line"] = -0.5
    df["macd_signal"] = 0.0
    df["macd_hist"] = -0.5
    df["rsi_14"] = 35.0
    df.iloc[-30, df.columns.get_loc("bos")] = "bear"
    df.iloc[-10, df.columns.get_loc("fvg")] = "bear"
    df.iloc[-5, df.columns.get_loc("order_block")] = "bear"
    df.iloc[-3, df.columns.get_loc("liquidity_sweep")] = "bear"
    return df


# --------------------------------------------------------------------
# BaseAgent + AgentSignal contract
# --------------------------------------------------------------------
def test_agent_signal_schema():
    from agents.base_agent import AgentSignal
    s = AgentSignal(agent="x", symbol="BTCUSDT", bias="Bullish", confidence=80.0,
                    reasoning="test", evidence={"a": 1})
    assert s.direction == "long"
    assert s.confidence_01 == 0.8


def test_agent_signal_validates_confidence_range():
    from agents.base_agent import AgentSignal
    with pytest.raises(Exception):
        AgentSignal(agent="x", symbol="BTC", confidence=150.0)
    with pytest.raises(Exception):
        AgentSignal(agent="x", symbol="BTC", confidence=-5.0)


def test_agent_signal_bias_values():
    from agents.base_agent import AgentSignal
    for b in ("Bullish", "Bearish", "Neutral"):
        s = AgentSignal(agent="x", symbol="BTC", bias=b)
        assert s.bias == b


# --------------------------------------------------------------------
# TrendAgent
# --------------------------------------------------------------------
@pytest.mark.asyncio
async def test_trend_agent_bullish():
    from agents.trend_agent import TrendAgent
    df = _bullish_feature_df()
    sig = await TrendAgent().analyze("BTCUSDT", features_df=df)
    assert sig.agent == "trend"
    assert sig.bias == "Bullish"
    assert 0 <= sig.confidence <= 100
    assert len(sig.reasoning) > 0
    assert "score" in sig.evidence


@pytest.mark.asyncio
async def test_trend_agent_bearish():
    from agents.trend_agent import TrendAgent
    df = _bearish_feature_df()
    sig = await TrendAgent().analyze("BTCUSDT", features_df=df)
    assert sig.bias == "Bearish"
    assert sig.confidence > 0


@pytest.mark.asyncio
async def test_trend_agent_handles_empty_df():
    from agents.trend_agent import TrendAgent
    sig = await TrendAgent().analyze("BTCUSDT", features_df=pd.DataFrame())
    assert sig.bias == "Neutral"
    assert sig.confidence == 0.0


@pytest.mark.asyncio
async def test_trend_agent_handles_missing_columns():
    from agents.trend_agent import TrendAgent
    df = pd.DataFrame({"close": [1, 2, 3]})
    sig = await TrendAgent().analyze("BTCUSDT", features_df=df)
    assert sig.bias == "Neutral"


# --------------------------------------------------------------------
# SMCAgent
# --------------------------------------------------------------------
@pytest.mark.asyncio
async def test_smc_agent_bullish():
    from agents.smc_agent import SMCAgent
    df = _bullish_feature_df()
    sig = await SMCAgent().analyze("BTCUSDT", features_df=df)
    assert sig.agent == "smc"
    assert sig.bias == "Bullish"
    assert "bull_bos" in sig.evidence
    assert "last_choch" in sig.evidence


@pytest.mark.asyncio
async def test_smc_agent_bearish():
    from agents.smc_agent import SMCAgent
    df = _bearish_feature_df()
    sig = await SMCAgent().analyze("BTCUSDT", features_df=df)
    assert sig.bias == "Bearish"


@pytest.mark.asyncio
async def test_smc_agent_handles_empty_df():
    from agents.smc_agent import SMCAgent
    sig = await SMCAgent().analyze("BTCUSDT", features_df=None)
    assert sig.bias == "Neutral"
    assert sig.confidence == 0.0


# --------------------------------------------------------------------
# DerivativesAgent
# --------------------------------------------------------------------
@pytest.mark.asyncio
async def test_derivatives_agent_basic():
    from agents.derivatives_agent import DerivativesAgent
    df = _feature_df()
    sig = await DerivativesAgent().analyze("BTCUSDT", features_df=df)
    assert sig.agent == "derivatives"
    assert sig.bias in {"Bullish", "Bearish", "Neutral"}
    assert 0 <= sig.confidence <= 100
    assert "funding_rate" in sig.evidence
    assert "long_short_ratio" in sig.evidence
    assert "cvd_latest" in sig.evidence


@pytest.mark.asyncio
async def test_derivatives_agent_cvd_slope_drives_bias():
    """Strong rising CVD should push bias bullish; falling should push bearish."""
    from agents.derivatives_agent import DerivativesAgent
    # Rising CVD
    df = _feature_df()
    df["cvd"] = np.linspace(0, 10000, len(df))  # strong uptrend
    df["funding_rate"] = 0.0
    df["long_short_ratio"] = 1.0
    sig = await DerivativesAgent().analyze("BTCUSDT", features_df=df)
    assert sig.bias in {"Bullish", "Neutral"}
    assert "cvd_slope" in sig.evidence
    assert sig.evidence["cvd_slope"] > 0

    # Falling CVD
    df2 = _feature_df()
    df2["cvd"] = np.linspace(10000, 0, len(df2))  # strong downtrend
    df2["funding_rate"] = 0.0
    df2["long_short_ratio"] = 1.0
    sig2 = await DerivativesAgent().analyze("BTCUSDT", features_df=df2)
    assert sig2.bias in {"Bearish", "Neutral"}
    assert sig2.evidence["cvd_slope"] < 0


@pytest.mark.asyncio
async def test_derivatives_agent_handles_empty_df():
    from agents.derivatives_agent import DerivativesAgent
    sig = await DerivativesAgent().analyze("BTCUSDT", features_df=None)
    assert sig.bias == "Neutral"
    assert sig.confidence == 0.0


# --------------------------------------------------------------------
# MacroAgent
# --------------------------------------------------------------------
@pytest.mark.asyncio
async def test_macro_agent_dxy_down_bullish():
    """DXY down + US10Y down should produce a bullish macro bias."""
    from agents.macro_agent import MacroAgent
    dxy_df = pd.DataFrame(
        {"close": np.linspace(105, 100, 30)},
        index=pd.date_range("2025-01-01", periods=30, freq="1h", tz="UTC"),
    )
    us10y_df = pd.DataFrame(
        {"close": np.linspace(4.5, 4.0, 30)},
        index=pd.date_range("2025-01-01", periods=30, freq="1h", tz="UTC"),
    )
    sig = await MacroAgent().analyze("BTCUSDT", dxy_df=dxy_df, us10y_df=us10y_df)
    assert sig.agent == "macro"
    assert sig.bias == "Bullish"
    assert "dxy_slope" in sig.evidence
    assert "us10y_slope" in sig.evidence


@pytest.mark.asyncio
async def test_macro_agent_dxy_up_bearish():
    from agents.macro_agent import MacroAgent
    dxy_df = pd.DataFrame(
        {"close": np.linspace(100, 105, 30)},
        index=pd.date_range("2025-01-01", periods=30, freq="1h", tz="UTC"),
    )
    us10y_df = pd.DataFrame(
        {"close": np.linspace(4.0, 4.5, 30)},
        index=pd.date_range("2025-01-01", periods=30, freq="1h", tz="UTC"),
    )
    sig = await MacroAgent().analyze("BTCUSDT", dxy_df=dxy_df, us10y_df=us10y_df)
    assert sig.bias == "Bearish"


@pytest.mark.asyncio
async def test_macro_agent_mixed_signals_neutral():
    from agents.macro_agent import MacroAgent
    dxy_df = pd.DataFrame(
        {"close": np.linspace(100, 105, 30)},  # DXY up = bearish
        index=pd.date_range("2025-01-01", periods=30, freq="1h", tz="UTC"),
    )
    us10y_df = pd.DataFrame(
        {"close": np.linspace(4.5, 4.0, 30)},  # US10Y down = bullish
        index=pd.date_range("2025-01-01", periods=30, freq="1h", tz="UTC"),
    )
    sig = await MacroAgent().analyze("BTCUSDT", dxy_df=dxy_df, us10y_df=us10y_df)
    # Should be Neutral since signals cancel
    assert sig.bias == "Neutral"


@pytest.mark.asyncio
async def test_macro_agent_handles_missing_data():
    from agents.macro_agent import MacroAgent
    sig = await MacroAgent().analyze("BTCUSDT")
    assert sig.bias == "Neutral"


def test_macro_agent_phase1_compat():
    """Phase 1 imports MacroAgent — must still subclass BaseAgent + name='macro'."""
    from agents.base_agent import BaseAgent
    from agents.macro_agent import MacroAgent
    assert issubclass(MacroAgent, BaseAgent)
    assert MacroAgent.name == "macro"


# --------------------------------------------------------------------
# SessionAgent
# --------------------------------------------------------------------
@pytest.mark.asyncio
async def test_session_agent_detects_sessions():
    """Verify session classification by UTC hour."""
    from agents.session_agent import _session_for_utc
    assert _session_for_utc(datetime(2025, 1, 1, 3, 0, tzinfo=timezone.utc)) == "Asian"
    assert _session_for_utc(datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)) == "London"
    assert _session_for_utc(datetime(2025, 1, 1, 18, 0, tzinfo=timezone.utc)) == "NewYork"


@pytest.mark.asyncio
async def test_session_agent_returns_signal():
    from agents.session_agent import SessionAgent
    df = _feature_df(n=100)
    sig = await SessionAgent().analyze("BTCUSDT", features_df=df,
                                        now_utc=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc))
    assert sig.agent == "session"
    assert sig.bias in {"Bullish", "Bearish", "Neutral"}
    assert 0 <= sig.confidence <= 100
    assert "current_session" in sig.evidence
    assert "prior_session" in sig.evidence
    assert sig.evidence["current_session"] == "London"


@pytest.mark.asyncio
async def test_session_agent_handles_non_datetime_index():
    from agents.session_agent import SessionAgent
    df = pd.DataFrame({"close": [1, 2, 3], "volume": [100, 200, 300]},
                      index=[0, 1, 2])
    sig = await SessionAgent().analyze("BTCUSDT", features_df=df)
    assert sig.bias == "Neutral"


# --------------------------------------------------------------------
# SentimentAgent
# --------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sentiment_agent_returns_neutral_50():
    from agents.sentiment_agent import SentimentAgent
    sig = await SentimentAgent().analyze("BTCUSDT")
    assert sig.agent == "sentiment"
    assert sig.bias == "Neutral"
    assert sig.confidence == 50.0
    assert "TODO" in sig.reasoning or "placeholder" in sig.reasoning.lower()


def test_sentiment_agent_phase1_compat():
    """Phase 1 imports SentimentAgent — must still subclass BaseAgent + name='sentiment'."""
    from agents.base_agent import BaseAgent
    from agents.sentiment_agent import SentimentAgent
    assert issubclass(SentimentAgent, BaseAgent)
    assert SentimentAgent.name == "sentiment"


# --------------------------------------------------------------------
# RetailTrapAgent
# --------------------------------------------------------------------
@pytest.mark.asyncio
async def test_retail_trap_agent_returns_trap_probabilities():
    from agents.retail_trap_agent import RetailTrapAgent, TrapAnalysis
    df = _feature_df(n=200)
    # Engineer some equal highs/lows + liquidity sweeps
    df.iloc[-10, df.columns.get_loc("equal_highs")] = True
    df.iloc[-8, df.columns.get_loc("equal_lows")] = True
    df.iloc[-5, df.columns.get_loc("liquidity_sweep")] = "bull"
    sig = await RetailTrapAgent().analyze("BTCUSDT", features_df=df)
    assert isinstance(sig, TrapAnalysis)
    assert sig.agent == "retail_trap"
    assert "stop_hunt_probability" in sig.trap_probabilities
    assert "fake_breakout_probability" in sig.trap_probabilities
    assert "short_squeeze_probability" in sig.trap_probabilities
    assert "long_squeeze_probability" in sig.trap_probabilities
    for key, val in sig.trap_probabilities.items():
        assert 0.0 <= val <= 1.0, f"{key}={val} not in [0, 1]"


@pytest.mark.asyncio
async def test_retail_trap_agent_short_squeeze_when_shorts_crowded():
    """L/S ratio < 0.7 + funding < -0.0003 + bull BOS -> high short squeeze prob."""
    from agents.retail_trap_agent import RetailTrapAgent
    df = _bullish_feature_df()
    df["long_short_ratio"] = 0.5  # shorts crowded
    df["funding_rate"] = -0.0008  # shorts paying hard
    df.iloc[-30, df.columns.get_loc("bos")] = "bull"
    sig = await RetailTrapAgent().analyze("BTCUSDT", features_df=df)
    assert sig.trap_probabilities["short_squeeze_probability"] > 0.4


@pytest.mark.asyncio
async def test_retail_trap_agent_long_squeeze_when_longs_crowded():
    from agents.retail_trap_agent import RetailTrapAgent
    df = _bearish_feature_df()
    df["long_short_ratio"] = 1.8  # longs crowded
    df["funding_rate"] = 0.0008  # longs paying hard
    df.iloc[-30, df.columns.get_loc("bos")] = "bear"
    sig = await RetailTrapAgent().analyze("BTCUSDT", features_df=df)
    assert sig.trap_probabilities["long_squeeze_probability"] > 0.4


@pytest.mark.asyncio
async def test_retail_trap_agent_handles_empty_df():
    from agents.retail_trap_agent import RetailTrapAgent
    sig = await RetailTrapAgent().analyze("BTCUSDT", features_df=None)
    assert sig.bias == "Neutral"
    for v in sig.trap_probabilities.values():
        assert v == 0.0


@pytest.mark.asyncio
async def test_retail_trap_agent_handles_no_sweeps():
    """RetailTrapAgent must not crash when there are zero liquidity sweeps."""
    from agents.retail_trap_agent import RetailTrapAgent
    df = _feature_df(n=200)
    # Ensure no sweeps, no equal highs/lows, no BOS
    df["liquidity_sweep"] = pd.Series([np.nan] * len(df), index=df.index, dtype="object")
    df["equal_highs"] = False
    df["equal_lows"] = False
    df["bos"] = pd.Series([np.nan] * len(df), index=df.index, dtype="object")
    # Should NOT raise IndexError
    sig = await RetailTrapAgent().analyze("BTCUSDT", features_df=df)
    assert sig.agent == "retail_trap"
    assert sig.bias in {"Bullish", "Bearish", "Neutral"}
    for v in sig.trap_probabilities.values():
        assert 0.0 <= v <= 1.0


# --------------------------------------------------------------------
# RiskAgent
# --------------------------------------------------------------------
@pytest.mark.asyncio
async def test_risk_agent_bullish_plan():
    from agents.risk_agent import RiskAgent, TradePlan
    df = _feature_df()
    sig = await RiskAgent().analyze(
        "BTCUSDT", features_df=df, entry=100.0, direction="Bullish",
        atr=2.0, capital=10_000, conviction=80,
    )
    assert isinstance(sig, TradePlan)
    assert sig.agent == "risk"
    assert sig.bias == "Bullish"
    assert sig.entry == 100.0
    # SL = 100 - 1.5 * 2 = 97
    assert abs(sig.stop_loss - 97.0) < 0.001
    # r = 3, TP1 = 100 + 3 = 103, TP2 = 100 + 6 = 106
    assert abs(sig.take_profit_1 - 103.0) < 0.001
    assert abs(sig.take_profit_2 - 106.0) < 0.001
    # Position size = 1% of 10000 / 3 = 33.33
    assert abs(sig.position_size - 33.333333) < 0.01
    assert sig.risk_reward_ratio == 1.0
    assert 0 <= sig.trade_safety_score <= 100


@pytest.mark.asyncio
async def test_risk_agent_bearish_plan():
    from agents.risk_agent import RiskAgent, TradePlan
    df = _feature_df()
    sig = await RiskAgent().analyze(
        "BTCUSDT", features_df=df, entry=100.0, direction="Bearish",
        atr=2.0, capital=10_000, conviction=80,
    )
    assert isinstance(sig, TradePlan)
    assert sig.bias == "Bearish"
    # SL = 100 + 1.5 * 2 = 103
    assert abs(sig.stop_loss - 103.0) < 0.001
    # r = 3, TP1 = 100 - 3 = 97, TP2 = 100 - 6 = 94
    assert abs(sig.take_profit_1 - 97.0) < 0.001
    assert abs(sig.take_profit_2 - 94.0) < 0.001


@pytest.mark.asyncio
async def test_risk_agent_neutral_returns_no_trade():
    from agents.risk_agent import RiskAgent, TradePlan
    sig = await RiskAgent().analyze(
        "BTCUSDT", entry=100.0, direction="Neutral", atr=2.0,
    )
    assert isinstance(sig, TradePlan)
    assert sig.bias == "Neutral"
    assert sig.stop_loss is None
    assert sig.position_size == 0.0
    assert sig.trade_safety_score == 0.0


@pytest.mark.asyncio
async def test_risk_agent_handles_missing_atr():
    from agents.risk_agent import RiskAgent
    sig = await RiskAgent().analyze(
        "BTCUSDT", entry=100.0, direction="Bullish", atr=None,
    )
    assert sig.bias == "Neutral"
    assert sig.confidence == 0.0


@pytest.mark.asyncio
async def test_risk_agent_infers_entry_and_atr_from_features():
    from agents.risk_agent import RiskAgent
    df = _feature_df()
    last_close = float(df["close"].iloc[-1])
    last_atr = float(df["atr_14"].iloc[-1])
    sig = await RiskAgent().analyze(
        "BTCUSDT", features_df=df, direction="Bullish",
    )
    assert sig.entry == last_close
    # SL = last_close - 1.5 * last_atr
    assert abs(sig.stop_loss - (last_close - 1.5 * last_atr)) < 0.001


@pytest.mark.asyncio
async def test_risk_agent_safety_score_increases_with_conviction():
    from agents.risk_agent import RiskAgent
    df = _feature_df()
    sig_low = await RiskAgent().analyze(
        "BTCUSDT", features_df=df, entry=100, direction="Bullish", atr=2, conviction=20,
    )
    sig_high = await RiskAgent().analyze(
        "BTCUSDT", features_df=df, entry=100, direction="Bullish", atr=2, conviction=90,
    )
    assert sig_high.trade_safety_score > sig_low.trade_safety_score


# --------------------------------------------------------------------
# Agent registry / imports
# --------------------------------------------------------------------
def test_all_phase5_agents_importable():
    import importlib
    for mod in [
        "agents.trend_agent", "agents.smc_agent", "agents.derivatives_agent",
        "agents.macro_agent", "agents.session_agent", "agents.sentiment_agent",
        "agents.retail_trap_agent", "agents.risk_agent",
    ]:
        assert importlib.import_module(mod) is not None


def test_all_agents_subclass_base_agent():
    from agents.base_agent import BaseAgent
    from agents.trend_agent import TrendAgent
    from agents.smc_agent import SMCAgent
    from agents.derivatives_agent import DerivativesAgent
    from agents.macro_agent import MacroAgent
    from agents.session_agent import SessionAgent
    from agents.sentiment_agent import SentimentAgent
    from agents.retail_trap_agent import RetailTrapAgent
    from agents.risk_agent import RiskAgent
    for cls in (TrendAgent, SMCAgent, DerivativesAgent, MacroAgent,
                SessionAgent, SentimentAgent, RetailTrapAgent, RiskAgent):
        assert issubclass(cls, BaseAgent), f"{cls.__name__} must subclass BaseAgent"


def test_all_agent_names_unique():
    from agents.trend_agent import TrendAgent
    from agents.smc_agent import SMCAgent
    from agents.derivatives_agent import DerivativesAgent
    from agents.macro_agent import MacroAgent
    from agents.session_agent import SessionAgent
    from agents.sentiment_agent import SentimentAgent
    from agents.retail_trap_agent import RetailTrapAgent
    from agents.risk_agent import RiskAgent
    names = [cls.name for cls in (TrendAgent, SMCAgent, DerivativesAgent, MacroAgent,
                                   SessionAgent, SentimentAgent, RetailTrapAgent, RiskAgent)]
    assert len(names) == len(set(names)), f"Duplicate agent names: {names}"


def test_phase1_agents_still_present():
    """Phase 1 stubs (TechnicalAgent, FundamentalAgent) must still be importable."""
    from agents.technical_agent import TechnicalAgent
    from agents.fundamental_agent import FundamentalAgent
    from agents.base_agent import BaseAgent
    assert issubclass(TechnicalAgent, BaseAgent)
    assert issubclass(FundamentalAgent, BaseAgent)
    assert TechnicalAgent.name == "technical"
    assert FundamentalAgent.name == "fundamental"


def test_agents_init_exports_all():
    """agents/__init__.py must export all Phase 5 agents + Phase 1 compat."""
    import agents
    for name in [
        "BaseAgent", "AgentSignal", "AgentOutput", "Bias",
        "TrendAgent", "SMCAgent", "DerivativesAgent", "MacroAgent",
        "SessionAgent", "SentimentAgent", "RetailTrapAgent", "TrapAnalysis",
        "RiskAgent", "TradePlan",
        "TechnicalAgent", "FundamentalAgent",
    ]:
        assert hasattr(agents, name), f"agents.{name} missing"
