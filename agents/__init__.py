"""
agents — Multi-agent framework for Aegis Quant AI.

Each specialized agent inherits from `BaseAgent` and produces an
`AgentSignal` (bias / confidence 0..100 / reasoning). The Chief Agent
in `/chief` orchestrates and aggregates their outputs into a single
conviction score.

Phase 5 agents:
  - TrendAgent         (EMA + MACD + RSI)
  - SMCAgent           (BOS / CHOCH / FVG / OB / Liquidity)
  - DerivativesAgent   (OI / Funding / L-S / CVD)
  - MacroAgent         (DXY + US10Y rule-based)
  - SessionAgent       (Asian / London / NewYork detection)
  - SentimentAgent     (placeholder — Neutral/50)
  - RetailTrapAgent    (trap probabilities)
  - RiskAgent          (SL / TP1 / TP2 / size / R-R / safety)
"""
from agents.base_agent import AgentSignal, AgentOutput, BaseAgent, Bias
from agents.trend_agent import TrendAgent
from agents.smc_agent import SMCAgent
from agents.derivatives_agent import DerivativesAgent
from agents.macro_agent import MacroAgent
from agents.session_agent import SessionAgent
from agents.sentiment_agent import SentimentAgent
from agents.retail_trap_agent import RetailTrapAgent, TrapAnalysis
from agents.risk_agent import RiskAgent, TradePlan

# Phase 1 stubs (kept for backward compatibility)
from agents.technical_agent import TechnicalAgent
from agents.fundamental_agent import FundamentalAgent

__all__ = [
    "BaseAgent", "AgentSignal", "AgentOutput", "Bias",
    "TrendAgent", "SMCAgent", "DerivativesAgent", "MacroAgent",
    "SessionAgent", "SentimentAgent", "RetailTrapAgent", "TrapAnalysis",
    "RiskAgent", "TradePlan",
    # Phase 1 backward compat
    "TechnicalAgent", "FundamentalAgent",
]
