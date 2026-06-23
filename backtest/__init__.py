"""
backtest — Backtesting engine for Aegis Quant AI.

The engine is event-driven and asset-agnostic. It consumes a signal
DataFrame + a price DataFrame and simulates fills against realistic
slippage and commission models. Performance metrics are computed in
`backtest.metrics`.
"""
