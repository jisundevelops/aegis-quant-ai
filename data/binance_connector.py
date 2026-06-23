"""
data.binance_connector — Backward-compatible re-export shim.

Phase 1 shipped this filename with a stub class. Phase 3 moved the real
implementation to `data.binance`. This module re-exports the real class
so existing imports (`from data.binance_connector import BinanceConnector`)
continue to work without any changes.
"""
from __future__ import annotations

from data.binance import BinanceConnector

__all__ = ["BinanceConnector"]
