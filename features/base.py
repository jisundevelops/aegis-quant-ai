"""
features.base — Abstract base class for all feature modules.

A feature is a deterministic, side-effect-free transformation of an OHLCV
DataFrame into a wider DataFrame containing one or more new columns.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class BaseFeature(ABC):
    """Abstract base class for all features.

    Subclasses set `name` and implement `compute()`. Features MUST NOT
    mutate the input DataFrame.
    """

    name: str = "base"

    @abstractmethod
    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return a new DataFrame with this feature's columns appended."""
        raise NotImplementedError

    @property
    def metadata(self) -> dict[str, str]:
        return {"feature": self.name, "version": "0.1.0"}

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r}>"
