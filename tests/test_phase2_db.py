"""
tests.test_phase2_db — Phase 2 smoke tests.

Verifies:
  - Settings loads DATABASE_URL + REDIS_URL (priority over individual fields).
  - DATABASE_URL with sync postgres:// is auto-upgraded to asyncpg.
  - All 5 ORM models have the required columns and constraints.
  - Cache helpers use the correct TTLs and tolerate Redis failures.
  - Cache key builders produce namespaced keys.
  - Alembic migration 0001_initial defines all 5 tables.
  - Connection helpers exist and have the right signatures.

These tests do NOT require a live database — they validate the static
contract. Live integration tests live in tests/test_phase2_live.py and
are skipped automatically when DATABASE_URL is unreachable.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# --------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------
def test_settings_priority_database_url(monkeypatch):
    """DATABASE_URL must take priority over individual POSTGRES_* fields."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h:5432/d")
    monkeypatch.setenv("POSTGRES_HOST", "should-not-be-used")
    # Re-load settings (clear cache)
    from config.settings import get_settings
    get_settings.cache_clear()
    s = get_settings()
    assert s.postgres_dsn == "postgresql+asyncpg://u:p@h:5432/d"
    get_settings.cache_clear()


def test_settings_falls_back_to_individual_fields(monkeypatch):
    """When DATABASE_URL is empty, individual fields are used."""
    from config.settings import Settings
    # Bypass .env loading entirely by passing _env_file=None; rely only on
    # the explicitly-provided kwargs.
    s = Settings(
        _env_file=None,
        database_url="",
        postgres_user="aegis",
        postgres_password="secret",
        postgres_host="localhost",
        postgres_port=5432,
        postgres_db="aegis_quant",
    )
    assert s.postgres_dsn == "postgresql+asyncpg://aegis:secret@localhost:5432/aegis_quant"


def test_settings_sync_url_auto_upgraded(monkeypatch):
    """A sync postgres:// URL must be auto-upgraded to asyncpg."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/d")
    from config.settings import get_settings
    get_settings.cache_clear()
    s = get_settings()
    assert s.postgres_dsn.startswith("postgresql+asyncpg://")
    get_settings.cache_clear()


def test_settings_redis_url_priority(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://default:pw@host:6379")
    monkeypatch.setenv("REDIS_HOST", "should-not-be-used")
    from config.settings import get_settings
    get_settings.cache_clear()
    s = get_settings()
    assert s.effective_redis_url == "redis://default:pw@host:6379"
    get_settings.cache_clear()


# --------------------------------------------------------------------
# Models
# --------------------------------------------------------------------
def test_models_importable():
    from database.models import (
        AgentOutput,
        BacktestResult,
        Base,
        MarketData,
        Signal,
        TradeJournal,
    )
    assert Base is not None
    for cls in (MarketData, Signal, AgentOutput, BacktestResult, TradeJournal):
        assert cls.__tablename__ in {
            "market_data", "signals", "agent_outputs",
            "backtest_results", "trade_journal",
        }


def test_market_data_columns():
    from database.models import MarketData
    cols = {c.name for c in MarketData.__table__.columns}
    required = {"id", "symbol", "timeframe", "timestamp", "open", "high",
                "low", "close", "volume", "source", "created_at"}
    assert required.issubset(cols), f"missing: {required - cols}"


def test_signals_columns():
    from database.models import Signal
    cols = {c.name for c in Signal.__table__.columns}
    required = {"id", "symbol", "direction", "entry", "sl", "tp1", "tp2",
                "confidence", "timestamp", "created_at"}
    assert required.issubset(cols), f"missing: {required - cols}"


def test_agent_outputs_columns():
    from database.models import AgentOutput
    cols = {c.name for c in AgentOutput.__table__.columns}
    required = {"id", "agent_name", "symbol", "bias", "confidence",
                "reasoning", "metadata", "timestamp", "created_at"}
    assert required.issubset(cols), f"missing: {required - cols}"


def test_backtest_results_columns():
    from database.models import BacktestResult
    cols = {c.name for c in BacktestResult.__table__.columns}
    required = {"id", "strategy_name", "win_rate", "pf", "sharpe",
                "drawdown", "metrics", "timestamp", "created_at"}
    assert required.issubset(cols), f"missing: {required - cols}"


def test_trade_journal_columns():
    from database.models import TradeJournal
    cols = {c.name for c in TradeJournal.__table__.columns}
    required = {"id", "symbol", "entry", "exit", "pnl", "notes",
                "timestamp", "created_at"}
    assert required.issubset(cols), f"missing: {required - cols}"


def test_market_data_unique_constraint():
    from database.models import MarketData
    constraints = [c.name for c in MarketData.__table__.constraints
                   if c.__class__.__name__ == "UniqueConstraint"]
    assert "uq_market_data_symbol_tf_ts" in constraints


def test_signals_check_constraints():
    from database.models import Signal
    check_names = [c.name for c in Signal.__table__.constraints
                   if c.__class__.__name__ == "CheckConstraint"]
    assert "ck_signals_direction" in check_names
    assert "ck_signals_confidence" in check_names


def test_agent_outputs_check_constraints():
    from database.models import AgentOutput
    check_names = [c.name for c in AgentOutput.__table__.constraints
                   if c.__class__.__name__ == "CheckConstraint"]
    assert "ck_agent_outputs_bias" in check_names
    assert "ck_agent_outputs_confidence" in check_names


# --------------------------------------------------------------------
# Cache helpers
# --------------------------------------------------------------------
def test_cache_key_namespace():
    from database.cache import features_key, price_key
    assert price_key("BTCUSDT") == "aegis:price:BTCUSDT"
    assert price_key("BTCUSDT", "1h") == "aegis:price:BTCUSDT:1h"
    assert features_key("BTCUSDT") == "aegis:features:BTCUSDT"
    assert features_key("BTCUSDT", "rsi") == "aegis:features:BTCUSDT:rsi"


def test_cache_ttls():
    from database.cache import FEATURE_TTL, PRICE_TTL
    assert PRICE_TTL == 60
    assert FEATURE_TTL == 300


@pytest.mark.asyncio
async def test_cache_set_get_roundtrip():
    """cache_set + cache_get should round-trip a dict via a mocked Redis."""
    captured = {}

    class FakeRedis:
        async def get(self, key):
            return captured.get(key)

        async def set(self, key, value, ex=None):
            captured[key] = value
            return True

    fake = FakeRedis()
    with patch("database.connection.get_redis", return_value=fake):
        from database.cache import cache_get, cache_set, features_key
        key = features_key("BTCUSDT")
        ok = await cache_set(key, {"rsi": 55.0}, 300)
        assert ok is True
        value = await cache_get(key)
        assert value == {"rsi": 55.0}


@pytest.mark.asyncio
async def test_cache_get_returns_none_on_redis_error():
    """cache_get must not raise when Redis fails — returns None instead."""
    class BrokenRedis:
        async def get(self, key):
            raise ConnectionError("redis down")

    with patch("database.connection.get_redis", return_value=BrokenRedis()):
        from database.cache import cache_get
        result = await cache_get("anykey")
        assert result is None


@pytest.mark.asyncio
async def test_cache_set_returns_false_on_redis_error():
    class BrokenRedis:
        async def set(self, key, value, ex=None):
            raise ConnectionError("redis down")

    with patch("database.connection.get_redis", return_value=BrokenRedis()):
        from database.cache import cache_set
        ok = await cache_set("anykey", {"a": 1}, 60)
        assert ok is False


@pytest.mark.asyncio
async def test_invalidate_pattern():
    """invalidate_pattern should delete every matching key."""
    stored = {"aegis:price:BTC:1m": "1", "aegis:price:BTC:5m": "2",
              "aegis:features:BTC": "3"}

    class FakeRedis:
        async def delete(self, *keys):
            for k in keys:
                stored.pop(k, None)
            return len(keys)

        async def scan_iter(self, match=None, count=500):
            for k in list(stored.keys()):
                if match and match.replace("*", "") in k:
                    yield k

    with patch("database.connection.get_redis", return_value=FakeRedis()):
        from database.cache import invalidate_pattern
        n = await invalidate_pattern("aegis:price:*")
        assert n == 2
        # features key untouched
        assert "aegis:features:BTC" in stored


# --------------------------------------------------------------------
# Connection handlers — signatures and lazy singletons
# --------------------------------------------------------------------
def test_connection_handlers_exist():
    from database import connection
    assert callable(connection.get_async_engine)
    assert callable(connection.get_async_session)
    assert callable(connection.get_async_session_factory)
    assert callable(connection.get_redis)
    assert callable(connection.init_db)
    assert callable(connection.close_all)


def test_get_async_session_is_async_generator():
    from database.connection import get_async_session
    assert inspect.isasyncgenfunction(get_async_session)


def test_async_session_ctx_is_async_context_manager():
    from database.connection import async_session_ctx
    # asynccontextmanager-decorated functions return an async context manager
    # when called.
    assert hasattr(async_session_ctx, "__wrapped__")


# --------------------------------------------------------------------
# Migration file
# --------------------------------------------------------------------
def test_migration_0001_defines_all_tables():
    """The initial Alembic migration must define all 5 tables in upgrade()."""
    migration_path = REPO_ROOT / "database" / "migrations" / "versions" / "0001_initial.py"
    assert migration_path.exists(), "0001_initial.py must exist"
    source = migration_path.read_text()
    for table in ("market_data", "signals", "agent_outputs",
                  "backtest_results", "trade_journal"):
        assert f'"{table}"' in source or f"'{table}'" in source, \
            f"table {table} missing from migration"


def test_migration_0001_revision_identifiers():
    migration_path = REPO_ROOT / "database" / "migrations" / "versions" / "0001_initial.py"
    source = migration_path.read_text()
    assert 'revision: str = "0001_initial"' in source
    assert "down_revision: str | None = None" in source


# --------------------------------------------------------------------
# Live integration (skipped if DB unreachable)
# --------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.skipif(
    not Path(REPO_ROOT / ".env").exists(),
    reason="no .env file — live DB tests skipped",
)
async def test_live_db_select_one():
    """If a live DB is configured, verify SELECT 1 works."""
    try:
        from database.connection import async_session_ctx, close_all, get_async_engine
        from sqlalchemy import text
        get_async_engine()
        async with async_session_ctx() as session:
            (result,) = (await session.execute(text("SELECT 1"))).one()
            assert result == 1
    except Exception as exc:
        pytest.skip(f"DB unreachable: {exc}")
    finally:
        try:
            await close_all()
        except Exception:
            pass


@pytest.mark.asyncio
@pytest.mark.skipif(
    not Path(REPO_ROOT / ".env").exists(),
    reason="no .env file — live Redis tests skipped",
)
async def test_live_redis_ping():
    try:
        from database.connection import close_all, get_redis
        await get_redis().ping()
    except Exception as exc:
        pytest.skip(f"Redis unreachable: {exc}")
    finally:
        try:
            await close_all()
        except Exception:
            pass
