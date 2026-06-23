"""
backend.core.logging — Loguru-based logging configuration.

Call `configure_logging()` once at application startup. Every other module
imports `logger` directly from `loguru`.
"""
from __future__ import annotations

import sys

from loguru import logger

from config import settings


def configure_logging() -> None:
    """Install a stdout sink with the configured log level."""
    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.log_level,
        backtrace=False,
        diagnose=False,
        enqueue=True,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> "
            "| <level>{level: <8}</level> "
            "| <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> "
            "- <level>{message}</level>"
        ),
    )
    logger.info("Logging configured (level={})", settings.log_level)


__all__ = ["configure_logging", "logger"]
