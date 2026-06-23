"""
data.validator — Market data quality validator.

Validates an OHLCV DataFrame against a small set of institutional-grade
sanity rules:

  1. Missing candles  — detect gaps in the time index larger than the
                        timeframe's expected interval.
  2. Duplicate timestamps — multiple rows sharing the same timestamp.
  3. Zero / null values — any of OHLCV being NaN, None, or zero where
                          a strictly-positive value is expected (O/H/L/C).

The validator produces a structured `ValidationReport` containing every
issue found, plus summary properties used by the connectors for logging.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd
from loguru import logger

# --------------------------------------------------------------------
# Timeframe -> expected timedelta
# --------------------------------------------------------------------
_TIMEFRAME_DELTAS: dict[str, pd.Timedelta] = {
    "15m": pd.Timedelta(minutes=15),
    "1h": pd.Timedelta(hours=1),
    "4h": pd.Timedelta(hours=4),
    "1d": pd.Timedelta(days=1),
}

# Columns where a strictly-positive value is expected
_PRICE_COLUMNS: tuple[str, ...] = ("open", "high", "low", "close")

IssueLevel = Literal["error", "warning"]


@dataclass
class ValidationIssue:
    """A single validation issue."""

    level: IssueLevel
    rule: str
    message: str
    rows: list = field(default_factory=list)


@dataclass
class ValidationReport:
    """Aggregated validation result for a single DataFrame."""

    symbol: str
    timeframe: str
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.level == "warning"]

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    @property
    def has_warnings(self) -> bool:
        return bool(self.warnings)

    @property
    def error_summary(self) -> str:
        return "; ".join(f"[{i.rule}] {i.message}" for i in self.errors)

    @property
    def warning_summary(self) -> str:
        return "; ".join(f"[{i.rule}] {i.message}" for i in self.warnings)


class DataValidator:
    """Validates OHLCV DataFrames for missing candles, duplicates, and bad values."""

    def validate(
        self,
        df: pd.DataFrame,
        *,
        symbol: str,
        timeframe: str,
    ) -> ValidationReport:
        """Run all validation rules against `df`.

        Parameters
        ----------
        df        : OHLCV DataFrame indexed by tz-aware timestamp
        symbol    : for reporting only
        timeframe : one of 15m / 1h / 4h / 1d
        """
        report = ValidationReport(symbol=symbol, timeframe=timeframe)

        if df is None or df.empty:
            report.issues.append(ValidationIssue(
                level="error",
                rule="empty_dataframe",
                message=f"DataFrame for {symbol} {timeframe} is empty",
            ))
            return report

        # Run all checks
        self._check_duplicates(df, report)
        self._check_missing_candles(df, report, timeframe)
        self._check_null_values(df, report)
        self._check_zero_values(df, report)

        # Log warnings
        for issue in report.warnings:
            logger.warning("Validator [{}] {} {}: {}",
                           issue.rule, symbol, timeframe, issue.message)
        for issue in report.errors:
            logger.error("Validator [{}] {} {}: {}",
                         issue.rule, symbol, timeframe, issue.message)

        return report

    # ----------------------------------------------------------------
    # Rule: duplicate timestamps
    # ----------------------------------------------------------------
    def _check_duplicates(self, df: pd.DataFrame, report: ValidationReport) -> None:
        if df.index.duplicated().any():
            dup_count = int(df.index.duplicated().sum())
            dup_ts = df.index[df.index.duplicated()].unique()[:5].tolist()
            report.issues.append(ValidationIssue(
                level="error",
                rule="duplicate_timestamps",
                message=f"{dup_count} duplicate timestamps detected",
                rows=dup_ts,
            ))

    # ----------------------------------------------------------------
    # Rule: missing candles (gaps in time index)
    # ----------------------------------------------------------------
    def _check_missing_candles(
        self, df: pd.DataFrame, report: ValidationReport, timeframe: str
    ) -> None:
        delta = _TIMEFRAME_DELTAS.get(timeframe)
        if delta is None:
            report.issues.append(ValidationIssue(
                level="warning",
                rule="unknown_timeframe",
                message=f"No expected-delta mapping for timeframe {timeframe!r}; gap check skipped",
            ))
            return

        if len(df) < 2:
            return  # Not enough bars to detect gaps

        # Sort by timestamp
        idx = pd.DatetimeIndex(sorted(df.index))
        diffs = idx.to_series().diff().dropna()

        # Tolerate gaps of up to 1.5x the expected delta (weekends, holidays)
        threshold = delta * 1.5
        gaps = diffs[diffs > threshold]
        if not gaps.empty:
            gap_count = len(gaps)
            sample_gaps = [
                {"from": gaps.index[i - 1].isoformat() if i > 0 else None,
                 "to": gaps.index[i].isoformat(),
                 "gap": str(gaps.iloc[i])}
                for i in range(min(5, gap_count))
            ]
            report.issues.append(ValidationIssue(
                level="warning",
                rule="missing_candles",
                message=f"{gap_count} gap(s) > {threshold} detected in {timeframe} series",
                rows=sample_gaps,
            ))

    # ----------------------------------------------------------------
    # Rule: null / NaN values in price columns
    # ----------------------------------------------------------------
    def _check_null_values(self, df: pd.DataFrame, report: ValidationReport) -> None:
        for col in _PRICE_COLUMNS:
            if col not in df.columns:
                report.issues.append(ValidationIssue(
                    level="error",
                    rule="missing_column",
                    message=f"Required column {col!r} not present in DataFrame",
                ))
                continue
            null_count = int(df[col].isna().sum())
            if null_count > 0:
                report.issues.append(ValidationIssue(
                    level="error",
                    rule="null_values",
                    message=f"{null_count} null/NaN values in column {col!r}",
                    rows=df.index[df[col].isna()].tolist()[:5],
                ))

        # Volume can legitimately be zero for some assets (FX), but
        # NaN is never OK.
        if "volume" in df.columns:
            vol_null = int(df["volume"].isna().sum())
            if vol_null > 0:
                report.issues.append(ValidationIssue(
                    level="warning",
                    rule="null_volume",
                    message=f"{vol_null} null/NaN values in 'volume' column",
                    rows=df.index[df["volume"].isna()].tolist()[:5],
                ))

    # ----------------------------------------------------------------
    # Rule: zero values where strictly-positive is expected
    # ----------------------------------------------------------------
    def _check_zero_values(self, df: pd.DataFrame, report: ValidationReport) -> None:
        for col in _PRICE_COLUMNS:
            if col not in df.columns:
                continue
            zero_count = int((df[col] == 0).sum())
            if zero_count > 0:
                report.issues.append(ValidationIssue(
                    level="error",
                    rule="zero_values",
                    message=f"{zero_count} zero values in price column {col!r}",
                    rows=df.index[df[col] == 0].tolist()[:5],
                ))


__all__ = ["DataValidator", "ValidationReport", "ValidationIssue"]
