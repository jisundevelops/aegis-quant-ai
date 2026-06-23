-- ============================================================
-- Aegis Quant AI — Core PostgreSQL schema
-- Phase 2 revision. The authoritative source of truth is the
-- Alembic migration at database/migrations/versions/0001_initial.py.
-- This SQL file is provided as a convenience for fresh installs that
-- do not use Alembic. Both must be kept in sync.
-- ============================================================

-- Required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trigram";
CREATE EXTENSION IF NOT EXISTS "btree_gin";

-- ============================================================
-- 1. market_data
-- ============================================================
CREATE TABLE IF NOT EXISTS market_data (
    id         BIGSERIAL    PRIMARY KEY,
    symbol     VARCHAR(32)  NOT NULL,
    timeframe  VARCHAR(8)   NOT NULL,
    timestamp  TIMESTAMPTZ  NOT NULL,
    open       NUMERIC(28,10) NOT NULL,
    high       NUMERIC(28,10) NOT NULL,
    low        NUMERIC(28,10) NOT NULL,
    close      NUMERIC(28,10) NOT NULL,
    volume     NUMERIC(28,10) NOT NULL DEFAULT 0,
    source     VARCHAR(32)  NOT NULL DEFAULT 'unknown',
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (symbol, timeframe, timestamp)
);
CREATE INDEX IF NOT EXISTS ix_market_data_symbol_ts   ON market_data (symbol, timestamp);
CREATE INDEX IF NOT EXISTS ix_market_data_timeframe   ON market_data (timeframe);

-- ============================================================
-- 2. signals
-- ============================================================
CREATE TABLE IF NOT EXISTS signals (
    id         BIGSERIAL    PRIMARY KEY,
    symbol     VARCHAR(32)  NOT NULL,
    direction  VARCHAR(8)   NOT NULL CHECK (direction IN ('long','short','flat')),
    entry      NUMERIC(20,8) NOT NULL,
    sl         NUMERIC(20,8),
    tp1        NUMERIC(20,8),
    tp2        NUMERIC(20,8),
    confidence NUMERIC(5,4) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    timestamp  TIMESTAMPTZ  NOT NULL,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_signals_symbol_ts ON signals (symbol, timestamp);

-- ============================================================
-- 3. agent_outputs
-- ============================================================
CREATE TABLE IF NOT EXISTS agent_outputs (
    id          BIGSERIAL    PRIMARY KEY,
    agent_name  VARCHAR(32)  NOT NULL,
    symbol      VARCHAR(32)  NOT NULL,
    bias        VARCHAR(8)   NOT NULL CHECK (bias IN ('bullish','bearish','neutral')),
    confidence  NUMERIC(5,4) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    reasoning   TEXT         NOT NULL DEFAULT '',
    metadata    JSONB        NOT NULL DEFAULT '{}'::jsonb,
    timestamp   TIMESTAMPTZ  NOT NULL,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_agent_outputs_agent_ts  ON agent_outputs (agent_name, timestamp);
CREATE INDEX IF NOT EXISTS ix_agent_outputs_symbol_ts ON agent_outputs (symbol, timestamp);

-- ============================================================
-- 4. backtest_results
-- ============================================================
CREATE TABLE IF NOT EXISTS backtest_results (
    id            BIGSERIAL    PRIMARY KEY,
    strategy_name VARCHAR(128) NOT NULL,
    win_rate      NUMERIC(6,4) NOT NULL,
    pf            NUMERIC(12,4) NOT NULL,                       -- profit factor
    sharpe        NUMERIC(10,4) NOT NULL,
    drawdown      NUMERIC(8,4)  NOT NULL,                       -- negative fraction
    metrics       JSONB        NOT NULL DEFAULT '{}'::jsonb,
    timestamp     TIMESTAMPTZ  NOT NULL,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_backtest_results_strategy_ts
    ON backtest_results (strategy_name, timestamp);

-- ============================================================
-- 5. trade_journal
-- ============================================================
CREATE TABLE IF NOT EXISTS trade_journal (
    id         BIGSERIAL    PRIMARY KEY,
    symbol     VARCHAR(32)  NOT NULL,
    entry      NUMERIC(20,8) NOT NULL,
    exit       NUMERIC(20,8),
    pnl        NUMERIC(20,8),
    notes      TEXT         NOT NULL DEFAULT '',
    timestamp  TIMESTAMPTZ  NOT NULL,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_trade_journal_symbol_ts
    ON trade_journal (symbol, timestamp);
