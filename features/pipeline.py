"""
features.pipeline — Feature pipeline orchestrator.

A `FeaturePipeline` accepts an ordered list of `BaseFeature` instances and
applies them sequentially to an OHLCV DataFrame, producing a wide feature
frame ready for the ML / agent layers.
"""
from __future__ import annotations

import pandas as pd

from features.base import BaseFeature


class FeaturePipeline:
    """Sequentially apply a list of features to a DataFrame."""

    def __init__(self, features: list[BaseFeature] | None = None) -> None:
        self.features: list[BaseFeature] = list(features or [])

    def add(self, feature: BaseFeature) -> "FeaturePipeline":
        self.features.append(feature)
        return self

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply all features in declaration order; return the wide frame."""
        out = df
        for f in self.features:
            out = f.compute(out)
        return out

    @property
    def feature_names(self) -> list[str]:
        return [f.name for f in self.features]

    def __repr__(self) -> str:
        return f"<FeaturePipeline features={self.feature_names}>"
