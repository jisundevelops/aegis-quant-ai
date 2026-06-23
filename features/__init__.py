"""
features — Feature engineering modules for Aegis Quant AI.

Each feature (indicator, microstructure metric, custom transform) is a
class that implements `compute(df) -> df`. The pipeline orchestrator runs
features in declaration order and returns a wide feature frame.
"""
from features.base import BaseFeature

__all__ = ["BaseFeature"]
