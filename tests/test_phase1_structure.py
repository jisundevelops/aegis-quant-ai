"""
tests.test_phase1_structure — Smoke tests for the Phase 1 scaffold.

Verifies that:
  - All top-level packages are importable.
  - The Settings object loads from .env.example defaults.
  - The FastAPI app can be instantiated.
  - Every agent / feature / connector class is present with the right name.

Run:  pytest tests/test_phase1_structure.py -v
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def test_settings_loads():
    from config import settings

    assert settings.app_name == "Aegis Quant AI"
    assert settings.app_version == "0.1.0"
    assert settings.app_port == 8000


def test_fastapi_app_instantiates():
    from backend.main import app

    assert app.title == "Aegis Quant AI"


def test_agents_present():
    from agents.base_agent import BaseAgent
    from agents.technical_agent import TechnicalAgent
    from agents.fundamental_agent import FundamentalAgent
    from agents.sentiment_agent import SentimentAgent
    from agents.macro_agent import MacroAgent

    for cls in (TechnicalAgent, FundamentalAgent, SentimentAgent, MacroAgent):
        assert issubclass(cls, BaseAgent)
        assert cls().name in {"technical", "fundamental", "sentiment", "macro"}


def test_features_present():
    from features.base import BaseFeature
    from features.indicators import RSI, MACD, EMA, ATR, BollingerBands

    for cls in (RSI, MACD, EMA, ATR, BollingerBands):
        assert issubclass(cls, BaseFeature)


def test_connectors_present():
    from data.base_connector import BaseConnector
    from data.binance_connector import BinanceConnector
    from data.yahoo_connector import YahooConnector
    from data.mt5_connector import MT5Connector

    for cls in (BinanceConnector, YahooConnector, MT5Connector):
        assert issubclass(cls, BaseConnector)


def test_backtest_classes_present():
    from backtest.engine import BacktestConfig, BacktestResult, BacktestEngine

    assert BacktestEngine().config.initial_capital == 100_000.0


def test_risk_classes_present():
    from risk.manager import RiskManager
    from risk.limits import RiskLimits

    rm = RiskManager()
    assert rm.limits.max_portfolio_leverage == 1.0


def test_chief_and_probability_present():
    from chief.orchestrator import ChiefAgent
    from probability.engine import ProbabilityEngine, ConvictionResult

    assert ChiefAgent().name == "chief"
    assert ProbabilityEngine().method == "bayesian"


@pytest.mark.parametrize(
    "module",
    [
        "config",
        "config.settings",
        "backend",
        "backend.main",
        "backend.api.routes.health",
        "backend.api.routes.market_data",
        "backend.api.routes.signals",
        "backend.core.logging",
        "backend.core.exceptions",
        "backend.schemas.market_data",
        "backend.schemas.signals",
        "agents",
        "agents.base_agent",
        "agents.technical_agent",
        "agents.fundamental_agent",
        "agents.sentiment_agent",
        "agents.macro_agent",
        "features",
        "features.base",
        "features.indicators",
        "features.microstructure",
        "features.pipeline",
        "data",
        "data.base_connector",
        "data.binance_connector",
        "data.yahoo_connector",
        "data.mt5_connector",
        "backtest",
        "backtest.engine",
        "backtest.portfolio",
        "backtest.metrics",
        "backtest.report",
        "risk",
        "risk.manager",
        "risk.position_sizing",
        "risk.limits",
        "chief",
        "chief.orchestrator",
        "probability",
        "probability.engine",
    ],
)
def test_module_importable(module: str):
    assert importlib.import_module(module) is not None
