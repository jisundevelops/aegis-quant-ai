"""
backtest.report — HTML / Markdown backtest report generator.

Phase 7 (or 8) implements the templated report. Today this module ships
the dataclass and entrypoint signature.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backtest.engine import BacktestResult


@dataclass
class ReportConfig:
    output_dir: Path = Path("reports")
    format: str = "html"  # 'html' | 'markdown' | 'pdf'


class ReportGenerator:
    """Render a `BacktestResult` into a shareable report."""

    def __init__(self, config: ReportConfig | None = None) -> None:
        self.config = config or ReportConfig()

    def generate(self, result: BacktestResult, name: str = "backtest") -> Path:
        """Generate the report file. Phase 7+."""
        raise NotImplementedError("ReportGenerator.generate() lands in Phase 7+.")
