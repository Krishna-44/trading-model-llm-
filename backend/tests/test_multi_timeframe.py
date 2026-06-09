"""Tests for agents.multi_timeframe — verify cross-timeframe alignment voting."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from aifos.agents.base import MarketContext
from aifos.agents.multi_timeframe import MultiTimeframeAgent


class _FakeProvider:
    """Provider that returns hand-shaped OHLC for each timeframe."""

    def __init__(self, frames: dict[str, pd.DataFrame]):
        self.frames = frames

    def history(self, symbol: str, interval: str) -> pd.DataFrame:
        return self.frames.get(interval, pd.DataFrame())


def _trending_up_df(n: int = 200, start: float = 100.0, drift: float = 0.5) -> pd.DataFrame:
    rng = np.arange(n, dtype=float)
    close = start + drift * rng + np.random.RandomState(0).normal(0, 0.3, n)
    return pd.DataFrame({
        "open": close, "high": close + 0.5, "low": close - 0.5, "close": close,
        "volume": np.full(n, 1000),
    })


def _trending_down_df(n: int = 200, start: float = 200.0, drift: float = -0.5) -> pd.DataFrame:
    return _trending_up_df(n=n, start=start, drift=drift)


def _flat_df(n: int = 200, mid: float = 100.0) -> pd.DataFrame:
    noise = np.random.RandomState(0).normal(0, 0.5, n)
    close = mid + noise
    return pd.DataFrame({
        "open": close, "high": close + 0.5, "low": close - 0.5, "close": close,
        "volume": np.full(n, 1000),
    })


def _ctx(symbol: str = "TEST.NS") -> MarketContext:
    return MarketContext(
        symbol=symbol, asset_class="equity",
        df=pd.DataFrame(), price=100.0, atr=1.0, equity=100000.0,
    )


def test_all_bullish_high_conf():
    provider = _FakeProvider({
        "15m": _trending_up_df(),
        "1h": _trending_up_df(),
        "1d": _trending_up_df(),
    })
    agent = MultiTimeframeAgent(provider=provider)
    op = agent.analyze(_ctx())
    assert op.stance == "bullish"
    assert op.confidence > 0.5


def test_all_bearish_high_conf():
    provider = _FakeProvider({
        "15m": _trending_down_df(),
        "1h": _trending_down_df(),
        "1d": _trending_down_df(),
    })
    agent = MultiTimeframeAgent(provider=provider)
    op = agent.analyze(_ctx())
    assert op.stance == "bearish"
    assert op.confidence > 0.5


def test_mixed_neutral_low_conf():
    provider = _FakeProvider({
        "15m": _trending_up_df(),
        "1h": _trending_down_df(),
        "1d": _flat_df(),
    })
    agent = MultiTimeframeAgent(provider=provider)
    op = agent.analyze(_ctx())
    # Either neutral or low-confidence directional
    assert op.confidence < 0.5


def test_no_provider_neutral_safe():
    agent = MultiTimeframeAgent(provider=None)
    op = agent.analyze(_ctx())
    # Should not crash; minimal confidence
    assert op.stance in ("bullish", "bearish", "neutral")
    assert 0.0 <= op.confidence <= 1.0


def test_provider_returns_empty_neutral():
    provider = _FakeProvider({"15m": pd.DataFrame(), "1h": pd.DataFrame(), "1d": pd.DataFrame()})
    agent = MultiTimeframeAgent(provider=provider)
    op = agent.analyze(_ctx())
    assert op.stance == "neutral"
    assert op.confidence == 0.0
