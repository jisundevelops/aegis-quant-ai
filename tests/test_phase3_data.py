"""
tests.test_phase3_data — Phase 3 smoke tests.

Verifies:
  - DataValidator detects: duplicates, missing candles, nulls, zeros.
  - DataValidator passes clean data.
  - BinanceConnector and YahooConnector are importable from BOTH the
    new module paths (data.binance / data.yahoo) and the backward-
    compatible shims (data.binance_connector / data.yahoo_connector).
  - Connectors have the right static config (symbols, intervals).
  - Scheduler has the right job schedule and lifecycle methods.
  - Settings.scheduler_enabled defaults to True.

Run:  pytest tests/test_phase3_data.py -v
"""
from __future__ import annotations

import sys
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
def _make_clean_ohlcv(n: int = 50, freq: str = "1h") -> pd.DataFrame:
    """Build a clean OHLCV DataFrame with no issues."""
    idx = pd.date_range("2025-01-01", periods=n, freq=freq, tz="UTC")
    return pd.DataFrame(
        {
            "open": np.linspace(100, 110, n),
            "high": np.linspace(101, 111, n),
            "low": np.linspace(99, 109, n),
            "close": np.linspace(100.5, 110.5, n),
            "volume": np.linspace(1000, 2000, n),
        },
        index=idx,
    )


# --------------------------------------------------------------------
# DataValidator
# --------------------------------------------------------------------
def test_validator_clean_data_passes():
    from data.validator import DataValidator
    df = _make_clean_ohlcv()
    report = DataValidator().validate(df, symbol="BTCUSDT", timeframe="1h")
    assert not report.has_errors
    assert not report.has_warnings


def test_validator_detects_duplicate_timestamps():
    from data.validator import DataValidator
    df = _make_clean_ohlcv()
    df = pd.concat([df, df.iloc[[0]]])  # duplicate the first row
    report = DataValidator().validate(df, symbol="BTCUSDT", timeframe="1h")
    assert report.has_errors
    rules = [i.rule for i in report.errors]
    assert "duplicate_timestamps" in rules


def test_validator_detects_missing_candles():
    from data.validator import DataValidator
    df = _make_clean_ohlcv(n=50, freq="1h")
    # Drop rows 10-19 (a 10-hour gap)
    df = df.drop(df.index[10:20])
    report = DataValidator().validate(df, symbol="BTCUSDT", timeframe="1h")
    assert report.has_warnings
    rules = [i.rule for i in report.warnings]
    assert "missing_candles" in rules


def test_validator_detects_null_values():
    from data.validator import DataValidator
    df = _make_clean_ohlcv()
    df.iloc[5, df.columns.get_loc("close")] = float("nan")
    report = DataValidator().validate(df, symbol="BTCUSDT", timeframe="1h")
    assert report.has_errors
    rules = [i.rule for i in report.errors]
    assert "null_values" in rules


def test_validator_detects_zero_values():
    from data.validator import DataValidator
    df = _make_clean_ohlcv()
    df.iloc[7, df.columns.get_loc("high")] = 0.0
    report = DataValidator().validate(df, symbol="BTCUSDT", timeframe="1h")
    assert report.has_errors
    rules = [i.rule for i in report.errors]
    assert "zero_values" in rules


def test_validator_handles_empty_dataframe():
    from data.validator import DataValidator
    df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    report = DataValidator().validate(df, symbol="BTCUSDT", timeframe="1h")
    assert report.has_errors
    assert any(i.rule == "empty_dataframe" for i in report.errors)


def test_validator_unknown_timeframe_emits_warning():
    from data.validator import DataValidator
    df = _make_clean_ohlcv()
    report = DataValidator().validate(df, symbol="BTCUSDT", timeframe="5m")
    # 5m isn't in our mapping, so a warning is expected
    assert any(i.rule == "unknown_timeframe" for i in report.warnings)


def test_validator_summary_strings():
    from data.validator import DataValidator
    df = _make_clean_ohlcv()
    df.iloc[0, df.columns.get_loc("open")] = float("nan")
    df.iloc[1, df.columns.get_loc("high")] = 0.0
    report = DataValidator().validate(df, symbol="BTCUSDT", timeframe="1h")
    assert "null_values" in report.error_summary
    assert "zero_values" in report.error_summary


# --------------------------------------------------------------------
# Connector imports (both new + shim paths)
# --------------------------------------------------------------------
def test_binance_connector_imports_from_new_path():
    from data.binance import BinanceConnector
    assert BinanceConnector.name == "binance"
    assert BinanceConnector.source == "binance"


def test_binance_connector_imports_from_shim_path():
    """Phase 1 imported from data.binance_connector — must still work."""
    from data.binance_connector import BinanceConnector as BC1
    from data.binance import BinanceConnector as BC2
    assert BC1 is BC2  # same class object


def test_yahoo_connector_imports_from_new_path():
    from data.yahoo import YahooConnector
    assert YahooConnector.name == "yahoo"
    assert YahooConnector.source == "yahoo"


def test_yahoo_connector_imports_from_shim_path():
    from data.yahoo_connector import YahooConnector as YC1
    from data.yahoo import YahooConnector as YC2
    assert YC1 is YC2


def test_binance_static_config():
    from data.binance import BinanceConnector
    assert "BTCUSDT" in BinanceConnector.symbols
    assert "ETHUSDT" in BinanceConnector.symbols
    for tf in ("15m", "1h", "4h", "1d"):
        assert tf in BinanceConnector.intervals


def test_yahoo_static_config():
    from data.yahoo import YahooConnector
    for s in ("EURUSD=X", "GC=F", "DX-Y.NYB", "^TNX"):
        assert s in YahooConnector.symbols
    # Yahoo uses "60m" internally but maps to "1h" in DB
    assert "60m" in YahooConnector.intervals


def test_binance_is_subclass_of_base_connector():
    from data.base_connector import BaseConnector
    from data.binance import BinanceConnector
    assert issubclass(BinanceConnector, BaseConnector)


def test_yahoo_is_subclass_of_base_connector():
    from data.base_connector import BaseConnector
    from data.yahoo import YahooConnector
    assert issubclass(YahooConnector, BaseConnector)


# --------------------------------------------------------------------
# Scheduler
# --------------------------------------------------------------------
def test_scheduler_lifecycle_functions_exist():
    from data.scheduler import start_scheduler, stop_scheduler, get_scheduler
    assert callable(start_scheduler)
    assert callable(stop_scheduler)
    assert callable(get_scheduler)


def test_scheduler_disabled_returns_none(monkeypatch):
    """When SCHEDULER_ENABLED=false, start_scheduler must return None."""
    from config.settings import Settings
    s = Settings(_env_file=None, scheduler_enabled=False)
    monkeypatch.setattr("data.scheduler.settings", s)
    from data.scheduler import start_scheduler
    result = start_scheduler()
    assert result is None


@pytest.mark.asyncio
async def test_scheduler_enabled_creates_jobs(monkeypatch):
    """When SCHEDULER_ENABLED=true, start_scheduler must register two jobs."""
    from config.settings import Settings
    s = Settings(_env_file=None, scheduler_enabled=True)
    monkeypatch.setattr("data.scheduler.settings", s)
    # Clear any singleton from earlier tests
    import data.scheduler as sch
    sch._scheduler = None
    sched = sch.start_scheduler()
    try:
        assert sched is not None
        job_ids = [j.id for j in sched.get_jobs()]
        assert "binance_fetch" in job_ids
        assert "yahoo_fetch" in job_ids
    finally:
        if sched is not None and sched.running:
            sched.shutdown(wait=False)
        sch._scheduler = None


@pytest.mark.asyncio
async def test_scheduler_job_triggers_use_correct_cadence(monkeypatch):
    """Binance job runs every 15 min; Yahoo job runs hourly at minute 5."""
    from config.settings import Settings
    s = Settings(_env_file=None, scheduler_enabled=True)
    monkeypatch.setattr("data.scheduler.settings", s)
    import data.scheduler as sch
    sch._scheduler = None
    sched = sch.start_scheduler()
    try:
        binance_job = sched.get_job("binance_fetch")
        yahoo_job = sched.get_job("yahoo_fetch")
        assert binance_job is not None
        assert yahoo_job is not None
        # Binance: minute="*/15" (every 15 min)
        # Yahoo: hour="*", minute="5" (every hour at minute 5)
        binance_trigger_str = str(binance_job.trigger)
        yahoo_trigger_str = str(yahoo_job.trigger)
        assert "0,15,30,45" in binance_trigger_str or "*/15" in binance_trigger_str
        assert "05" in yahoo_trigger_str or "5" in yahoo_trigger_str
    finally:
        if sched is not None and sched.running:
            sched.shutdown(wait=False)
        sch._scheduler = None


# --------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------
def test_settings_scheduler_enabled_default():
    from config.settings import Settings
    s = Settings(_env_file=None)
    assert s.scheduler_enabled is True


# --------------------------------------------------------------------
# Module importability
# --------------------------------------------------------------------
@pytest.mark.parametrize(
    "module",
    [
        "data.binance",
        "data.yahoo",
        "data.binance_connector",
        "data.yahoo_connector",
        "data.validator",
        "data.scheduler",
    ],
)
def test_phase3_module_importable(module: str):
    import importlib
    assert importlib.import_module(module) is not None
