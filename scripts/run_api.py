#!/usr/bin/env python
"""
scripts.run_api — Convenience launcher for the FastAPI backend.

Reads HOST/PORT from configuration and launches uvicorn.

Usage:
    python scripts/run_api.py
"""
from __future__ import annotations

import uvicorn

from config import settings


def main() -> None:
    uvicorn.run(
        "backend.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=not settings.is_production,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
