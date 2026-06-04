"""Strategy interface.

A strategy maps an OHLCV frame to a *target position* series in [-1, 1]:
  +1 = fully long, 0 = flat, -1 = fully short.
The backtester lags positions by one bar, so strategies may use the current
bar's close to decide the position they will hold *next* bar (no look-ahead).
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class StrategySignal:
    """A point-in-time read used by the Market Analyst agent."""
    target_position: float          # -1..1
    strength: float                 # 0..1 conviction from the rule itself
    rationale: str
    features: dict = field(default_factory=dict)


class Strategy(abc.ABC):
    name: str = "base"

    def __init__(self, **params) -> None:
        self.params = params

    @abc.abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """Return target position per bar, indexed like ``df`` (values in [-1,1])."""

    def latest_signal(self, df: pd.DataFrame) -> StrategySignal:
        """Point read for the live decision loop. Override for richer rationale."""
        sig = self.generate_signals(df)
        pos = float(sig.iloc[-1]) if len(sig) else 0.0
        return StrategySignal(
            target_position=pos,
            strength=min(1.0, abs(pos)),
            rationale=f"{self.name}: target position {pos:+.2f}",
        )

    def describe(self) -> dict:
        return {"name": self.name, "params": self.params}
