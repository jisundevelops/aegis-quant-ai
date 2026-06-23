"""
data — Market data connectors for Aegis Quant AI.

Each connector inherits from `BaseConnector` and implements the canonical
methods `fetch_ohlcv()`, `fetch_tick()`, and `fetch_symbols()`. Phase 2
ships the concrete implementations for Binance, Yahoo Finance, and
MetaTrader 5.
"""
from data.base_connector import BaseConnector

__all__ = ["BaseConnector"]
