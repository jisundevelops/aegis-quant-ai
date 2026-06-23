"""
data.yahoo_connector — Backward-compatible re-export shim.

Phase 1 shipped this filename with a stub class. Phase 3 moved the real
implementation to `data.yahoo`. This module re-exports the real class
so existing imports (`from data.yahoo_connector import YahooConnector`)
continue to work without any changes.
"""
from __future__ import annotations

from data.yahoo import YahooConnector

__all__ = ["YahooConnector"]
