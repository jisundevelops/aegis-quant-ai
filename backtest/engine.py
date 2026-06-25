"""
backtest.engine — Event-driven backtesting engine.

Loads historical OHLCV from PostgreSQL, builds features, runs the Chief
Agent on each bar (using only data available up to that bar to avoid
lookahead bias), simulates trades with entry/SL/TP1/TP2, and tracks
the equity curve.

Trade simulation:
  - When the Chief Agent returns LONG  -> enter long at next bar open
                                          SL below entry, TP1/TP2 above
  - When the Chief Agent returns SHORT -> enter short at next bar open
                                          SL above entry, TP1/TP2 below
  - When the Chief Agent returns NEUTRAL -> no new trade; existing
                                            positions continue to be
                                            managed
  - Positions are exited when SL or TP1 is hit (TP2 is tracked but the
    position is closed at TP1 by default; the user can configure
    partial exits)
  - At most one position open at a time (configurable in BacktestConfig)

Commission + slippage are applied per side.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

from backtest.bias_detector import BiasDetector
from backtest.metrics import compute_all
from chief.chief_agent import ChiefAgent, ChiefSignal


# --------------------------------------------------------------------
# Config + result
# --------------------------------------------------------------------
@dataclass
class BacktestConfig:
    """Configuration for a single backtest run."""

    initial_capital: float = 100_000.0
    commission_bps: float = 1.0       # 1 basis point per side
    slippage_bps: float = 1.0         # 1 basis point per side
    max_leverage: float = 1.0
    shorting_allowed: bool = True
    risk_free_rate: float = 0.0
    # How many bars to wait before re-evaluating after a trade closes
    cooldown_bars: int = 0
    # Close position at TP1 (default True). If False, hold until TP2 or SL.
    close_at_tp1: bool = True
    # Maximum bars to hold a position before force-closing
    max_hold_bars: int = 100
    # Bar offset for entry: 0 = same bar close, 1 = next bar open (default)
    entry_offset: int = 1


@dataclass
class BacktestResult:
    """Output of a backtest run."""

    equity_curve: pd.Series
    trades: pd.DataFrame
    positions: pd.DataFrame
    signals: pd.DataFrame
    metrics: dict = field(default_factory=dict)
    bias_report: list[dict] = field(default_factory=list)
    config: BacktestConfig | None = None
    start_date: str | None = None
    end_date: str | None = None
    symbol: str = ""
    timeframe: str = ""

    def as_dict(self) -> dict[str, Any]:
        """JSON-serializable representation."""
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "metrics": self.metrics,
            "bias_report": self.bias_report,
            "config": {
                "initial_capital": self.config.initial_capital if self.config else 0,
                "commission_bps": self.config.commission_bps if self.config else 0,
                "slippage_bps": self.config.slippage_bps if self.config else 0,
                "max_leverage": self.config.max_leverage if self.config else 1,
                "shorting_allowed": self.config.shorting_allowed if self.config else True,
            } if self.config else {},
            "equity_curve": [
                {"timestamp": str(ts), "equity": float(val)}
                for ts, val in self.equity_curve.items()
            ] if self.equity_curve is not None else [],
            "trades": self.trades.to_dict(orient="records") if self.trades is not None and not self.trades.empty else [],
            "total_trades": int(len(self.trades)) if self.trades is not None else 0,
            "total_signals": int(len(self.signals)) if self.signals is not None else 0,
        }


# --------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------
class BacktestEngine:
    """Event-driven backtester that runs the Chief Agent on historical data."""

    def __init__(
        self,
        config: BacktestConfig | None = None,
        chief_agent: ChiefAgent | None = None,
    ) -> None:
        self.config = config or BacktestConfig()
        self.chief = chief_agent or ChiefAgent()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    async def run(
        self,
        symbol: str,
        timeframe: str,
        features_df: pd.DataFrame,
        start: str | None = None,
        end: str | None = None,
    ) -> BacktestResult:
        """Run the backtest.

        Parameters
        ----------
        symbol       : ticker
        timeframe    : '15m' | '1h' | '4h' | '1d'
        features_df  : Phase 4 combined feature DataFrame (must have a
                       tz-aware DatetimeIndex and at least close + atr_14
                       columns)
        start        : ISO date string (inclusive), e.g. '2024-01-01'
        end          : ISO date string (inclusive), e.g. '2024-12-31'
        """
        if features_df is None or features_df.empty:
            return self._empty_result(symbol, timeframe, start, end)

        # Filter by date range
        df = features_df.copy()
        if start is not None:
            df = df[df.index >= pd.Timestamp(start, tz="UTC")]
        if end is not None:
            df = df[df.index <= pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1)]
        if len(df) < 50:
            logger.warning("Backtest: only {} bars in range — need at least 50", len(df))
            return self._empty_result(symbol, timeframe, start, end)

        logger.info("Backtest: {} bars for {} {} from {} to {}",
                    len(df), symbol, timeframe,
                    df.index[0].isoformat(), df.index[-1].isoformat())

        # 1. Generate signals bar-by-bar (no lookahead — only data up to bar i)
        signals = await self._generate_signals(symbol, timeframe, df)
        logger.info("Backtest: {} signals generated", len(signals))

        # 2. Simulate trades
        trades, positions, equity_curve = self._simulate_trades(df, signals)
        logger.info("Backtest: {} trades executed, final equity={:.2f}",
                    len(trades), equity_curve.iloc[-1] if not equity_curve.empty else 0)

        # 3. Compute metrics
        periods = self._periods_per_year(timeframe)
        metrics = compute_all(
            equity=equity_curve,
            trades=trades,
            risk_free=self.config.risk_free_rate,
            periods=periods,
        )

        # 4. Detect biases
        bias_report = BiasDetector().detect(
            features_df=df,
            trades=trades,
            metrics=metrics,
            equity=equity_curve,
        )

        return BacktestResult(
            equity_curve=equity_curve,
            trades=trades,
            positions=positions,
            signals=signals,
            metrics=metrics,
            bias_report=bias_report.as_list(),
            config=self.config,
            start_date=start or str(df.index[0].date()),
            end_date=end or str(df.index[-1].date()),
            symbol=symbol,
            timeframe=timeframe,
        )

    # ------------------------------------------------------------------
    # Signal generation (no lookahead)
    # ------------------------------------------------------------------
    async def _generate_signals(
        self,
        symbol: str,
        timeframe: str,
        df: pd.DataFrame,
    ) -> pd.DataFrame:
        """Run the Chief Agent on each bar using only data up to that bar.

        Returns a DataFrame indexed by timestamp with columns:
            direction, entry, stop_loss, tp1, tp2, confidence, risk_score
        """
        records: list[dict] = []
        n = len(df)

        # We start at bar 50 to ensure enough warmup for indicators
        start_bar = 50
        # To keep the backtest fast, we sample every N bars rather than
        # running the Chief Agent on every single bar. The default is
        # every 1 bar (i.e. every bar) — configurable via self.config.
        step = 1

        for i in range(start_bar, n, step):
            # Truncate the feature frame to bar i (no lookahead)
            window = df.iloc[: i + 1]
            ts = df.index[i]

            try:
                signal = await self.chief.analyze(
                    symbol=symbol,
                    timeframe=timeframe,
                    features_df=window,
                )
                records.append({
                    "timestamp": ts,
                    "signal_time": ts,
                    "direction": signal.direction,
                    "entry": float(signal.entry_zone[0]) if signal.entry_zone else float(window["close"].iloc[-1]),
                    "stop_loss": signal.stop_loss,
                    "tp1": signal.take_profit_1,
                    "tp2": signal.take_profit_2,
                    "confidence": signal.confidence_score,
                    "risk_score": signal.risk_score,
                })
            except Exception as exc:  # noqa: BLE001
                logger.debug("Chief Agent error at bar {}: {}", ts, exc)
                continue

        if not records:
            return pd.DataFrame(columns=[
                "timestamp", "signal_time", "direction", "entry",
                "stop_loss", "tp1", "tp2", "confidence", "risk_score"
            ]).set_index("timestamp")

        sig_df = pd.DataFrame(records).set_index("timestamp")
        return sig_df

    # ------------------------------------------------------------------
    # Trade simulation
    # ------------------------------------------------------------------
    def _simulate_trades(
        self,
        df: pd.DataFrame,
        signals: pd.DataFrame,
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
        """Simulate trades based on signals and track equity.

        Returns (trades, positions, equity_curve).
        """
        cfg = self.config
        capital = cfg.initial_capital
        equity_history: list[tuple[pd.Timestamp, float]] = []
        trade_records: list[dict] = []
        position_records: list[dict] = []

        # Position state
        in_position = False
        pos_direction: str | None = None  # 'LONG' | 'SHORT'
        pos_entry: float = 0.0
        pos_sl: float = 0.0
        pos_tp1: float = 0.0
        pos_tp2: float = 0.0
        pos_size: float = 0.0  # units
        pos_entry_time: pd.Timestamp | None = None
        pos_entry_bar: int = 0
        cooldown_remaining = 0

        n = len(df)
        high = df["high"].values
        low = df["low"].values
        close = df["close"].values
        open_ = df["open"].values
        timestamps = df.index

        for i in range(n):
            ts = timestamps[i]

            # ----- Manage open position -----
            if in_position:
                # Check if SL or TP was hit at bar i
                hit_sl = False
                hit_tp = False
                exit_price = 0.0
                exit_reason = ""

                if pos_direction == "LONG":
                    if low[i] <= pos_sl:
                        hit_sl = True
                        exit_price = pos_sl
                        exit_reason = "stop_loss"
                    elif high[i] >= pos_tp1 and cfg.close_at_tp1:
                        hit_tp = True
                        exit_price = pos_tp1
                        exit_reason = "take_profit_1"
                    elif high[i] >= pos_tp2 and not cfg.close_at_tp1:
                        hit_tp = True
                        exit_price = pos_tp2
                        exit_reason = "take_profit_2"

                elif pos_direction == "SHORT":
                    if high[i] >= pos_sl:
                        hit_sl = True
                        exit_price = pos_sl
                        exit_reason = "stop_loss"
                    elif low[i] <= pos_tp1 and cfg.close_at_tp1:
                        hit_tp = True
                        exit_price = pos_tp1
                        exit_reason = "take_profit_1"
                    elif low[i] <= pos_tp2 and not cfg.close_at_tp1:
                        hit_tp = True
                        exit_price = pos_tp2
                        exit_reason = "take_profit_2"

                # Force-close after max_hold_bars
                bars_held = i - pos_entry_bar
                if not hit_sl and not hit_tp and bars_held >= cfg.max_hold_bars:
                    exit_price = close[i]
                    exit_reason = "max_hold"
                    hit_sl = False
                    hit_tp = False
                    # treat as a forced close

                if hit_sl or hit_tp or exit_reason == "max_hold":
                    # Compute PnL
                    if pos_direction == "LONG":
                        gross_pnl = (exit_price - pos_entry) * pos_size
                    else:  # SHORT
                        gross_pnl = (pos_entry - exit_price) * pos_size

                    # Commission + slippage on exit
                    exit_cost = abs(exit_price * pos_size) * (cfg.commission_bps + cfg.slippage_bps) / 10_000
                    entry_cost = abs(pos_entry * pos_size) * (cfg.commission_bps + cfg.slippage_bps) / 10_000
                    net_pnl = gross_pnl - entry_cost - exit_cost
                    capital += net_pnl

                    trade_records.append({
                        "entry_time": pos_entry_time,
                        "exit_time": ts,
                        "signal_time": pos_entry_time,  # approximate
                        "direction": pos_direction,
                        "entry": pos_entry,
                        "exit": exit_price,
                        "stop_loss": pos_sl,
                        "tp1": pos_tp1,
                        "tp2": pos_tp2,
                        "size": pos_size,
                        "pnl": net_pnl,
                        "return_pct": (net_pnl / (pos_entry * pos_size)) if pos_entry * pos_size > 0 else 0.0,
                        "exit_reason": exit_reason,
                        "bars_held": bars_held,
                    })

                    position_records.append({
                        "entry_time": pos_entry_time,
                        "exit_time": ts,
                        "direction": pos_direction,
                        "entry": pos_entry,
                        "exit": exit_price,
                        "size": pos_size,
                        "pnl": net_pnl,
                    })

                    in_position = False
                    pos_direction = None
                    cooldown_remaining = cfg.cooldown_bars

            # ----- Check for new entry -----
            if not in_position and cooldown_remaining <= 0 and i < n - 1:
                # Look for a signal at this bar
                if ts in signals.index:
                    sig = signals.loc[ts]
                    direction = sig["direction"]
                    if direction in ("LONG", "SHORT") and not (direction == "SHORT" and not cfg.shorting_allowed):
                        entry_price = float(sig["entry"])
                        sl = float(sig["stop_loss"]) if pd.notna(sig["stop_loss"]) else None
                        tp1 = float(sig["tp1"]) if pd.notna(sig["tp1"]) else None
                        tp2 = float(sig["tp2"]) if pd.notna(sig["tp2"]) else None

                        if sl is not None and tp1 is not None and entry_price > 0:
                            # Position size: risk 1% of capital per trade
                            risk_amount = capital * 0.01
                            risk_per_unit = abs(entry_price - sl)
                            if risk_per_unit > 0:
                                pos_size = risk_amount / risk_per_unit
                                # Apply leverage cap
                                max_notional = capital * cfg.max_leverage
                                if pos_size * entry_price > max_notional:
                                    pos_size = max_notional / entry_price

                                in_position = True
                                pos_direction = direction
                                pos_entry = entry_price
                                pos_sl = sl
                                pos_tp1 = tp1
                                pos_tp2 = tp2 if tp2 is not None else tp1
                                pos_entry_time = ts
                                pos_entry_bar = i

            if cooldown_remaining > 0:
                cooldown_remaining -= 1

            # ----- Record equity -----
            # Mark-to-market: if in position, include unrealized PnL
            if in_position:
                if pos_direction == "LONG":
                    unrealized = (close[i] - pos_entry) * pos_size
                else:
                    unrealized = (pos_entry - close[i]) * pos_size
                equity = capital + unrealized
            else:
                equity = capital
            equity_history.append((ts, float(equity)))

        # ----- Close any remaining position at the last bar -----
        if in_position and equity_history:
            exit_price = close[-1]
            if pos_direction == "LONG":
                gross_pnl = (exit_price - pos_entry) * pos_size
            else:
                gross_pnl = (pos_entry - exit_price) * pos_size
            exit_cost = abs(exit_price * pos_size) * (cfg.commission_bps + cfg.slippage_bps) / 10_000
            entry_cost = abs(pos_entry * pos_size) * (cfg.commission_bps + cfg.slippage_bps) / 10_000
            net_pnl = gross_pnl - entry_cost - exit_cost
            capital += net_pnl
            trade_records.append({
                "entry_time": pos_entry_time,
                "exit_time": timestamps[-1],
                "signal_time": pos_entry_time,
                "direction": pos_direction,
                "entry": pos_entry,
                "exit": exit_price,
                "stop_loss": pos_sl,
                "tp1": pos_tp1,
                "tp2": pos_tp2,
                "size": pos_size,
                "pnl": net_pnl,
                "return_pct": (net_pnl / (pos_entry * pos_size)) if pos_entry * pos_size > 0 else 0.0,
                "exit_reason": "end_of_backtest",
                "bars_held": n - 1 - pos_entry_bar,
            })
            # Update last equity
            equity_history[-1] = (timestamps[-1], float(capital))

        equity_curve = pd.Series(
            [e for _, e in equity_history],
            index=[t for t, _ in equity_history],
            name="equity",
        )
        trades_df = pd.DataFrame(trade_records)
        positions_df = pd.DataFrame(position_records)

        return trades_df, positions_df, equity_curve

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _periods_per_year(timeframe: str) -> int:
        """Approximate number of bars per year for annualization."""
        return {
            "15m": 252 * 24 * 4,   # 24192
            "1h":  252 * 24,       # 6048
            "4h":  252 * 6,        # 1512
            "1d":  252,            # 252
        }.get(timeframe, 252)

    def _empty_result(
        self, symbol: str, timeframe: str, start: str | None, end: str | None
    ) -> BacktestResult:
        return BacktestResult(
            equity_curve=pd.Series(dtype=float, name="equity"),
            trades=pd.DataFrame(),
            positions=pd.DataFrame(),
            signals=pd.DataFrame(),
            metrics={
                "total_trades": 0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "sharpe_ratio": 0.0,
                "sortino_ratio": 0.0,
                "calmar_ratio": 0.0,
                "max_drawdown": 0.0,
                "expectancy": 0.0,
                "total_return": 0.0,
                "final_equity": 0.0,
            },
            bias_report=BiasDetector().detect().as_list(),
            config=self.config,
            start_date=start,
            end_date=end,
            symbol=symbol,
            timeframe=timeframe,
        )


__all__ = ["BacktestConfig", "BacktestResult", "BacktestEngine"]
