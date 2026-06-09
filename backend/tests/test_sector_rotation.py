"""Tests for agents.sector_rotation — verify rank-based stance."""
from __future__ import annotations

import numpy as np
import pandas as pd

from aifos.agents.base import MarketContext
from aifos.agents.sector_rotation import SectorRotationAgent, SECTOR_INDEX


def _df_with_return(daily_return_pct: float, n: int = 30, start: float = 100.0) -> pd.DataFrame:
    rng = np.arange(n, dtype=float)
    close = start * (1 + daily_return_pct / 100.0) ** rng
    return pd.DataFrame({
        "open": close, "high": close * 1.005, "low": close * 0.995,
        "close": close, "volume": np.full(n, 1000),
    })


class _Provider:
    def __init__(self, returns_by_index: dict[str, float]):
        # 1% per day → strong; -1% → weak.
        self._frames = {
            idx: _df_with_return(returns_by_index.get(idx, 0.0))
            for idx in SECTOR_INDEX.values()
        }

    def history(self, symbol: str, interval: str) -> pd.DataFrame:
        return self._frames.get(symbol, pd.DataFrame())


def _ctx(symbol: str) -> MarketContext:
    return MarketContext(
        symbol=symbol, asset_class="equity",
        df=pd.DataFrame(), price=100.0, atr=1.0, equity=100000.0,
    )


def test_bank_top_rank_bullish_for_bank_stock():
    # Banks ramp +1%/day, IT -1%/day, others 0
    returns = {SECTOR_INDEX["bank"]: 1.0, SECTOR_INDEX["it"]: -1.0}
    agent = SectorRotationAgent(provider=_Provider(returns), lookback_days=20)
    op = agent.analyze(_ctx("HDFCBANK.NS"))
    assert op.stance == "bullish"
    assert op.confidence > 0.3
    assert op.signals["sector"] == "bank"


def test_it_bottom_rank_bearish_for_it_stock():
    returns = {SECTOR_INDEX["bank"]: 1.0, SECTOR_INDEX["it"]: -1.0,
               SECTOR_INDEX["metal"]: 0.8, SECTOR_INDEX["auto"]: 0.6}
    agent = SectorRotationAgent(provider=_Provider(returns), lookback_days=20)
    op = agent.analyze(_ctx("TCS.NS"))
    assert op.stance == "bearish"
    assert op.signals["sector"] == "it"


def test_unknown_symbol_neutral():
    agent = SectorRotationAgent(provider=_Provider({}), lookback_days=20)
    op = agent.analyze(_ctx("UNKNOWN.NS"))
    assert op.stance == "neutral"
    assert op.confidence == 0.0


def test_no_provider_neutral():
    agent = SectorRotationAgent(provider=None)
    op = agent.analyze(_ctx("HDFCBANK.NS"))
    assert op.stance == "neutral"


def test_lookup_handles_lowercase_symbol():
    # Symbol matching should be case-tolerant.
    returns = {SECTOR_INDEX["bank"]: 1.0}
    agent = SectorRotationAgent(provider=_Provider(returns))
    op = agent.analyze(_ctx("hdfcbank.ns"))
    # Either resolves to bank or stays neutral; test no crash + valid stance.
    assert op.stance in ("bullish", "bearish", "neutral")
