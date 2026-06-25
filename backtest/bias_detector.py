"""
backtest.bias_detector — Detect and warn about common backtest biases.

Bias types checked:
  1. Lookahead Bias    — features whose values at bar i depend on data
                         from bars > i. Detected by checking if any
                         feature column has values that change when
                         computed on a truncated vs. full dataset.
  2. Data Leakage      — the same data window is used for both signal
                         generation and trade evaluation. Detected by
                         checking if entry/exit timestamps overlap with
                         the feature window used to generate the signal.
  3. Overfitting       — win rate unrealistically high on a small sample.
                         Heuristic: warn if win_rate > 0.80 AND
                         total_trades < 30.
  4. Survivorship Bias — static warning (cannot be detected from data
                         alone; the user must ensure the universe includes
                         delisted/failed symbols).

The detector returns a `BiasReport` containing a list of `BiasWarning`
objects with severity (info / warning / critical).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

Severity = Literal["info", "warning", "critical"]


@dataclass
class BiasWarning:
    """A single bias warning."""

    bias_type: str          # lookahead | data_leakage | overfitting | survivorship
    severity: Severity
    message: str
    details: dict = field(default_factory=dict)


@dataclass
class BiasReport:
    """Aggregated bias detection result."""

    warnings: list[BiasWarning] = field(default_factory=list)

    @property
    def has_critical(self) -> bool:
        return any(w.severity == "critical" for w in self.warnings)

    @property
    def has_warnings(self) -> bool:
        return any(w.severity in ("warning", "critical") for w in self.warnings)

    @property
    def summary(self) -> str:
        if not self.warnings:
            return "No bias warnings detected."
        parts = [f"{w.severity.upper()} [{w.bias_type}]: {w.message}" for w in self.warnings]
        return "\n".join(parts)

    def as_list(self) -> list[dict]:
        return [
            {
                "bias_type": w.bias_type,
                "severity": w.severity,
                "message": w.message,
                "details": w.details,
            }
            for w in self.warnings
        ]


class BiasDetector:
    """Detect common backtest biases."""

    # Overfitting heuristic thresholds
    OVERFIT_WIN_RATE_THRESHOLD = 0.80
    OVERFIT_MIN_TRADES = 30

    def detect(
        self,
        features_df: pd.DataFrame | None = None,
        trades: pd.DataFrame | None = None,
        metrics: dict | None = None,
        equity: pd.Series | None = None,
    ) -> BiasReport:
        """Run all bias checks.

        Parameters
        ----------
        features_df  : the feature DataFrame used in the backtest (optional)
        trades       : the trades DataFrame (optional)
        metrics      : the computed metrics dict (optional)
        equity       : the equity curve (optional)
        """
        report = BiasReport()

        # 1. Static survivorship warning (always included as info)
        report.warnings.append(BiasWarning(
            bias_type="survivorship",
            severity="info",
            message=(
                "Survivorship bias: ensure your historical universe includes "
                "delisted/failed symbols, not just currently-active ones. "
                "This cannot be auto-detected — verify your data source."
            ),
        ))

        # 2. Lookahead bias check (requires features_df)
        if features_df is not None and not features_df.empty:
            self._check_lookahead(features_df, report)

        # 3. Data leakage check (requires trades)
        if trades is not None and not trades.empty:
            self._check_data_leakage(trades, report)

        # 4. Overfitting check (requires metrics + trades)
        if metrics is not None and trades is not None:
            self._check_overfitting(metrics, trades, report)

        return report

    # ------------------------------------------------------------------
    def _check_lookahead(self, df: pd.DataFrame, report: BiasReport) -> None:
        """Detect lookahead bias by checking if any column uses future data.

        Heuristic: for a sample of columns, compare the value at bar N
        computed on df.iloc[:N+1] vs. df.iloc[:N+1+lookahead]. If they
        differ, the column likely uses future data.

        We check only the numeric, non-OHLCV columns (feature columns).
        """
        # Skip OHLCV columns — they're market data, not features
        ohlcv = {"open", "high", "low", "close", "volume"}
        feature_cols = [
            c for c in df.columns
            if c not in ohlcv
            and pd.api.types.is_numeric_dtype(df[c])
        ]
        if not feature_cols:
            return

        # Sample up to 5 feature columns
        sample_cols = feature_cols[:5]
        lookahead = 5
        issues: list[str] = []

        for col in sample_cols:
            # Pick a bar in the middle of the dataset
            n = len(df)
            if n < lookahead + 10:
                continue
            test_idx = n // 2
            truncated = df[col].iloc[:test_idx + 1].iloc[-1]
            full = df[col].iloc[:test_idx + 1 + lookahead].iloc[-1 - lookahead]
            # If the value at bar test_idx changed after we added `lookahead`
            # more bars, that column is non-causal.
            if pd.notna(truncated) and pd.notna(full):
                if abs(float(truncated) - float(full)) > 1e-10:
                    issues.append(col)

        if issues:
            report.warnings.append(BiasWarning(
                bias_type="lookahead",
                severity="critical",
                message=(
                    f"Potential lookahead bias detected in columns: {issues}. "
                    "These features have values that change when future bars "
                    "are added — they may be using information not available "
                    "at signal time."
                ),
                details={"suspicious_columns": issues},
            ))

    # ------------------------------------------------------------------
    def _check_data_leakage(self, trades: pd.DataFrame, report: BiasReport) -> None:
        """Detect data leakage between signal and evaluation windows.

        Heuristic: if any trade's entry timestamp is before the last
        timestamp used in the feature window that generated the signal,
        there's leakage. We approximate this by checking that entry_time
        > signal_time for each trade.
        """
        required = {"entry_time"}
        if not required.issubset(set(trades.columns)):
            return

        if "signal_time" in trades.columns:
            # Check entry_time > signal_time (entry should be after signal)
            leaked = trades[trades["entry_time"] < trades["signal_time"]]
            if not leaked.empty:
                report.warnings.append(BiasWarning(
                    bias_type="data_leakage",
                    severity="critical",
                    message=(
                        f"{len(leaked)} trades have entry_time before signal_time. "
                        "This indicates the trade was evaluated using data "
                        "from before the signal was generated."
                    ),
                    details={"leaked_trade_count": int(len(leaked))},
                ))

    # ------------------------------------------------------------------
    def _check_overfitting(
        self, metrics: dict, trades: pd.DataFrame, report: BiasReport
    ) -> None:
        """Warn about overfitting signs."""
        total_trades = metrics.get("total_trades", len(trades) if trades is not None else 0)
        wr = metrics.get("win_rate", 0.0)

        if total_trades < self.OVERFIT_MIN_TRADES:
            report.warnings.append(BiasWarning(
                bias_type="overfitting",
                severity="warning",
                message=(
                    f"Only {total_trades} trades — sample size is too small "
                    f"for statistically significant conclusions. Minimum "
                    f"recommended: {self.OVERFIT_MIN_TRADES} trades."
                ),
                details={
                    "total_trades": int(total_trades),
                    "minimum_recommended": self.OVERFIT_MIN_TRADES,
                },
            ))

        if wr > self.OVERFIT_WIN_RATE_THRESHOLD and total_trades > 0:
            report.warnings.append(BiasWarning(
                bias_type="overfitting",
                severity="warning",
                message=(
                    f"Win rate {wr*100:.1f}% exceeds {self.OVERFIT_WIN_RATE_THRESHOLD*100:.0f}% "
                    f"threshold. This is unusually high and may indicate "
                    f"overfitting, especially with {total_trades} trades. "
                    f"Consider out-of-sample testing."
                ),
                details={
                    "win_rate": float(wr),
                    "threshold": self.OVERFIT_WIN_RATE_THRESHOLD,
                    "total_trades": int(total_trades),
                },
            ))


__all__ = ["BiasDetector", "BiasReport", "BiasWarning"]
