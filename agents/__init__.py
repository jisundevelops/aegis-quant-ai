"""
agents — Multi-agent framework for Aegis Quant AI.

Each specialized agent (technical, fundamental, sentiment, macro) lives in
its own module and inherits from `BaseAgent`. The Chief Agent in `/chief`
orchestrates and aggregates their outputs into a single conviction score.
"""
from agents.base_agent import BaseAgent

__all__ = ["BaseAgent"]
