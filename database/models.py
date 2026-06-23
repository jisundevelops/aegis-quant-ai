"""
database.models — SQLAlchemy ORM models for Aegis Quant AI.

Tables (Phase 2 spec):
  - market_data      OHLCV bars indexed by (symbol, timeframe, timestamp)
  - signals          Aggregated trading signals with entry/SL/TPs
  - agent_outputs    Per-agent analysis outputs with bias + reasoning
  - backtest_results Performance summaries per backtest run
  - trade_journal    Manual / automated trade journal entries

Conventions:
  - All timestamps are timezone-aware UTC.
  - Numeric columns use NUMERIC to avoid float drift on prices and PnL.
  - Every table has a surrogate BIGSERIAL primary key.
  - Heavily-queried columns are indexed.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for all Aegis ORM models."""


# --------------------------------------------------------------------
# 1. market_data
# --------------------------------------------------------------------
class MarketData(Base):
    """OHLCV bars for a (symbol, timeframe) pair."""

    __tablename__ = "market_data"
    __table_args__ = (
        UniqueConstraint(
            "symbol", "timeframe", "timestamp", name="uq_market_data_symbol_tf_ts"
        ),
        Index("ix_market_data_symbol_ts", "symbol", "timestamp"),
        Index("ix_market_data_timeframe", "timeframe"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    open: Mapped[float] = mapped_column(Numeric(28, 10), nullable=False)
    high: Mapped[float] = mapped_column(Numeric(28, 10), nullable=False)
    low: Mapped[float] = mapped_column(Numeric(28, 10), nullable=False)
    close: Mapped[float] = mapped_column(Numeric(28, 10), nullable=False)
    volume: Mapped[float] = mapped_column(Numeric(28, 10), nullable=False, default=0)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<MarketData {self.symbol} {self.timeframe} "
            f"{self.timestamp} close={self.close}>"
        )


# --------------------------------------------------------------------
# 2. signals
# --------------------------------------------------------------------
class Signal(Base):
    """Aggregated trading signal with entry, SL and TP levels."""

    __tablename__ = "signals"
    __table_args__ = (
        CheckConstraint(
            "direction IN ('long', 'short', 'flat')", name="ck_signals_direction"
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_signals_confidence"
        ),
        Index("ix_signals_symbol_ts", "symbol", "timestamp"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    entry: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    sl: Mapped[float | None] = mapped_column(Numeric(20, 8), nullable=True)
    tp1: Mapped[float | None] = mapped_column(Numeric(20, 8), nullable=True)
    tp2: Mapped[float | None] = mapped_column(Numeric(20, 8), nullable=True)
    confidence: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<Signal {self.symbol} {self.direction} conf={self.confidence}>"


# --------------------------------------------------------------------
# 3. agent_outputs
# --------------------------------------------------------------------
class AgentOutput(Base):
    """Per-agent analysis output with bias, confidence and reasoning."""

    __tablename__ = "agent_outputs"
    __table_args__ = (
        CheckConstraint(
            "bias IN ('bullish', 'bearish', 'neutral')", name="ck_agent_outputs_bias"
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_agent_outputs_confidence",
        ),
        Index("ix_agent_outputs_agent_ts", "agent_name", "timestamp"),
        Index("ix_agent_outputs_symbol_ts", "symbol", "timestamp"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agent_name: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    bias: Mapped[str] = mapped_column(String(8), nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False, default="")
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="{}"
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<AgentOutput {self.agent_name} {self.symbol} "
            f"{self.bias} conf={self.confidence}>"
        )


# --------------------------------------------------------------------
# 4. backtest_results
# --------------------------------------------------------------------
class BacktestResult(Base):
    """Performance summary for a single backtest run."""

    __tablename__ = "backtest_results"
    __table_args__ = (
        Index("ix_backtest_results_strategy_ts", "strategy_name", "timestamp"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    strategy_name: Mapped[str] = mapped_column(String(128), nullable=False)
    win_rate: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)
    pf: Mapped[float] = mapped_column(
        Numeric(12, 4), nullable=False, comment="Profit factor"
    )
    sharpe: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    drawdown: Mapped[float] = mapped_column(
        Numeric(8, 4), nullable=False, comment="Max drawdown as a negative fraction"
    )
    metrics: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="{}", comment="Full metrics blob"
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<BacktestResult {self.strategy_name} "
            f"wr={self.win_rate} pf={self.pf} sharpe={self.sharpe}>"
        )


# --------------------------------------------------------------------
# 5. trade_journal
# --------------------------------------------------------------------
class TradeJournal(Base):
    """Trade journal entry (manual or auto-filled from backtest/live)."""

    __tablename__ = "trade_journal"
    __table_args__ = (
        Index("ix_trade_journal_symbol_ts", "symbol", "timestamp"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    entry: Mapped[float] = mapped_column(Numeric(20, 8), nullable=False)
    exit: Mapped[float | None] = mapped_column(Numeric(20, 8), nullable=True)
    pnl: Mapped[float | None] = mapped_column(Numeric(20, 8), nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<TradeJournal {self.symbol} entry={self.entry} pnl={self.pnl}>"


__all__ = [
    "Base",
    "MarketData",
    "Signal",
    "AgentOutput",
    "BacktestResult",
    "TradeJournal",
]
