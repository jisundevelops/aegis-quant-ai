"""
backtest.report — JSON report generator + PostgreSQL persistence.

Generates a JSON backtest report from a `BacktestResult` and saves a
summary row to the PostgreSQL `backtest_results` table (Phase 2 schema).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from backtest.engine import BacktestResult


@dataclass
class ReportConfig:
    output_dir: Path = Path("reports")
    format: str = "json"  # 'json' | 'markdown' (markdown reserved for future)


class ReportGenerator:
    """Render a `BacktestResult` into a JSON file + persist to PostgreSQL."""

    def __init__(self, config: ReportConfig | None = None) -> None:
        self.config = config or ReportConfig()

    # ------------------------------------------------------------------
    # JSON file generation
    # ------------------------------------------------------------------
    def generate_json(
        self,
        result: BacktestResult,
        name: str | None = None,
        save_to_db: bool = True,
    ) -> dict:
        """Generate a JSON-serializable report dict.

        Parameters
        ----------
        result     : the BacktestResult to report on
        name       : optional name for the backtest (defaults to symbol_tf_timestamp)
        save_to_db : if True, persist a summary row to PostgreSQL

        Returns
        -------
        The report as a dict (also written to a JSON file on disk if
        ReportConfig.output_dir is set).
        """
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backtest_name = name or f"{result.symbol}_{result.timeframe}_{ts}"

        report = {
            "name": backtest_name,
            "symbol": result.symbol,
            "timeframe": result.timeframe,
            "start_date": result.start_date,
            "end_date": result.end_date,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "metrics": result.metrics,
            "bias_report": result.bias_report,
            "config": {
                "initial_capital": result.config.initial_capital if result.config else 0,
                "commission_bps": result.config.commission_bps if result.config else 0,
                "slippage_bps": result.config.slippage_bps if result.config else 0,
                "max_leverage": result.config.max_leverage if result.config else 1,
                "shorting_allowed": result.config.shorting_allowed if result.config else True,
                "risk_free_rate": result.config.risk_free_rate if result.config else 0,
            } if result.config else {},
            "equity_curve": [
                {"timestamp": str(t), "equity": float(v)}
                for t, v in result.equity_curve.items()
            ] if result.equity_curve is not None else [],
            "trades": result.trades.to_dict(orient="records")
                      if result.trades is not None and not result.trades.empty
                      else [],
            "total_trades": int(len(result.trades)) if result.trades is not None else 0,
            "total_signals": int(len(result.signals)) if result.signals is not None else 0,
        }

        # Write to disk
        if self.config.output_dir:
            self.config.output_dir.mkdir(parents=True, exist_ok=True)
            out_path = self.config.output_dir / f"{backtest_name}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, default=str)
            logger.info("Backtest report written to {}", out_path)

        # Persist to PostgreSQL
        if save_to_db:
            try:
                import asyncio
                asyncio.get_event_loop().create_task(
                    self._save_to_db(result, backtest_name)
                ) if asyncio.get_event_loop().is_running() else asyncio.run(
                    self._save_to_db(result, backtest_name)
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not persist backtest to DB: {}", exc)

        return report

    # ------------------------------------------------------------------
    # PostgreSQL persistence
    # ------------------------------------------------------------------
    async def _save_to_db(self, result: BacktestResult, name: str) -> None:
        """Save a summary row to the backtest_results table."""
        from database.connection import async_session_ctx
        from database.models import BacktestResult as BacktestResultModel
        from sqlalchemy import insert

        metrics = result.metrics
        row = {
            "strategy_name": name,
            "win_rate": metrics.get("win_rate", 0.0),
            "pf": metrics.get("profit_factor", 0.0),
            "sharpe": metrics.get("sharpe_ratio", 0.0),
            "drawdown": metrics.get("max_drawdown", 0.0),
            "metrics": {
                **metrics,
                "bias_report": result.bias_report,
                "symbol": result.symbol,
                "timeframe": result.timeframe,
                "start_date": result.start_date,
                "end_date": result.end_date,
                "total_trades": int(len(result.trades)) if result.trades is not None else 0,
            },
            "timestamp": datetime.now(timezone.utc),
        }

        try:
            async with async_session_ctx() as session:
                stmt = insert(BacktestResultModel).values(row)
                await session.execute(stmt)
                await session.commit()
                logger.info("Backtest '{}' saved to PostgreSQL", name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("DB save failed for backtest '{}': {}", name, exc)


__all__ = ["ReportConfig", "ReportGenerator"]
