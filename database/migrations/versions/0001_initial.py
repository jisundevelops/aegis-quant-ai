"""Initial schema: market_data, signals, agent_outputs, backtest_results, trade_journal.

Revision ID: 0001_initial
Revises:
Create Date: 2025-01-01 00:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---- market_data ----
    op.create_table(
        "market_data",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(28, 10), nullable=False),
        sa.Column("high", sa.Numeric(28, 10), nullable=False),
        sa.Column("low", sa.Numeric(28, 10), nullable=False),
        sa.Column("close", sa.Numeric(28, 10), nullable=False),
        sa.Column("volume", sa.Numeric(28, 10), nullable=False, server_default="0"),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol", "timeframe", "timestamp", name="uq_market_data_symbol_tf_ts"),
    )
    op.create_index("ix_market_data_symbol_ts", "market_data", ["symbol", "timestamp"])
    op.create_index("ix_market_data_timeframe", "market_data", ["timeframe"])

    # ---- signals ----
    op.create_table(
        "signals",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("entry", sa.Numeric(20, 8), nullable=False),
        sa.Column("sl", sa.Numeric(20, 8), nullable=True),
        sa.Column("tp1", sa.Numeric(20, 8), nullable=True),
        sa.Column("tp2", sa.Numeric(20, 8), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("direction IN ('long', 'short', 'flat')", name="ck_signals_direction"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_signals_confidence"),
    )
    op.create_index("ix_signals_symbol_ts", "signals", ["symbol", "timestamp"])

    # ---- agent_outputs ----
    op.create_table(
        "agent_outputs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("agent_name", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("bias", sa.String(length=8), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=False, server_default=""),
        sa.Column("metadata", JSONB, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("bias IN ('bullish', 'bearish', 'neutral')", name="ck_agent_outputs_bias"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_agent_outputs_confidence"),
    )
    op.create_index("ix_agent_outputs_agent_ts", "agent_outputs", ["agent_name", "timestamp"])
    op.create_index("ix_agent_outputs_symbol_ts", "agent_outputs", ["symbol", "timestamp"])

    # ---- backtest_results ----
    op.create_table(
        "backtest_results",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("strategy_name", sa.String(length=128), nullable=False),
        sa.Column("win_rate", sa.Numeric(6, 4), nullable=False),
        sa.Column("pf", sa.Numeric(12, 4), nullable=False, comment="Profit factor"),
        sa.Column("sharpe", sa.Numeric(10, 4), nullable=False),
        sa.Column("drawdown", sa.Numeric(8, 4), nullable=False, comment="Max drawdown as a negative fraction"),
        sa.Column("metrics", JSONB, nullable=False, server_default=sa.text("'{}'"), comment="Full metrics blob"),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_backtest_results_strategy_ts", "backtest_results", ["strategy_name", "timestamp"])

    # ---- trade_journal ----
    op.create_table(
        "trade_journal",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("entry", sa.Numeric(20, 8), nullable=False),
        sa.Column("exit", sa.Numeric(20, 8), nullable=True),
        sa.Column("pnl", sa.Numeric(20, 8), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trade_journal_symbol_ts", "trade_journal", ["symbol", "timestamp"])


def downgrade() -> None:
    op.drop_index("ix_trade_journal_symbol_ts", table_name="trade_journal")
    op.drop_table("trade_journal")

    op.drop_index("ix_backtest_results_strategy_ts", table_name="backtest_results")
    op.drop_table("backtest_results")

    op.drop_index("ix_agent_outputs_symbol_ts", table_name="agent_outputs")
    op.drop_index("ix_agent_outputs_agent_ts", table_name="agent_outputs")
    op.drop_table("agent_outputs")

    op.drop_index("ix_signals_symbol_ts", table_name="signals")
    op.drop_table("signals")

    op.drop_index("ix_market_data_timeframe", table_name="market_data")
    op.drop_index("ix_market_data_symbol_ts", table_name="market_data")
    op.drop_table("market_data")
