"""TradingAgents-inspired additions: tuned consensus band + outcome-memory loop.

The bull/bear debate was found redundant with the existing weighted consensus and
SKIPPED. What's kept (evidence-backed): the consensus band tuned to 0.20 (OOS
loss-cutting), and wiring the idle MarketMemory so the committee conditions
confidence on how similar PAST setups resolved.
"""
from types import SimpleNamespace

import numpy as np
import pandas as pd

import aifos.memory.vector as mv
from aifos.agents.committee import _situation_features
from aifos.config import settings
from aifos.memory.vector import MarketMemory


def _ctx(close_vals, regime="trending", vol_ratio=1.0, atr=2.0, price=120.0):
    df = pd.DataFrame({"close": close_vals,
                       "high": [c * 1.01 for c in close_vals],
                       "low": [c * 0.99 for c in close_vals]})
    return SimpleNamespace(df=df, atr=atr, price=price,
                           extra={"regime": {"regime": regime, "vol_ratio": vol_ratio}})


def test_band_tuned_to_0_20():
    # the OOS sweet spot from the TradingAgents debate-gate backtest (loss-cutting)
    assert settings.consensus_dead_band == 0.20


def test_situation_features_shape_and_range():
    f = _situation_features(_ctx(list(np.linspace(100, 120, 60)), vol_ratio=1.2), net=0.4)
    assert len(f) == 5
    assert all(-1.001 <= x <= 1.001 for x in f)
    assert f[2] == 0.4  # net consensus is the 3rd feature


def test_situation_features_never_raises_on_short_series():
    f = _situation_features(_ctx([100.0, 101.0], regime="panic"), net=-0.3)
    assert len(f) == 5 and f[2] == -0.3


def test_memory_writeback_and_haircut_logic(tmp_path, monkeypatch):
    monkeypatch.setattr(mv, "_STORE_PATH", str(tmp_path / "mem.pkl"))
    m = MarketMemory()
    feats = [0.5, 0.1, 0.4, 0.5, 0.2]
    # a setup that historically LOST 6 times
    for _ in range(6):
        m.add(feats, {"outcome": "loss", "symbol": "X", "pnl": -100})
    nb = [x for x in m.query(feats, k=8)
          if x.get("outcome") in ("win", "loss") and x.get("similarity", 0.0) >= 0.5]
    assert len(nb) >= settings.memory_min_neighbors
    wr = sum(1 for x in nb if x["outcome"] == "win") / len(nb)
    assert wr < 0.45                      # -> the committee would haircut confidence
    factor = max(0.5, wr / 0.5)
    assert factor == 0.5                  # all-loss neighbourhood -> max haircut (conf x0.5)


def test_memory_no_haircut_when_winners(tmp_path, monkeypatch):
    monkeypatch.setattr(mv, "_STORE_PATH", str(tmp_path / "mem2.pkl"))
    m = MarketMemory()
    feats = [0.2, 0.0, 0.3, 0.0, 0.1]
    for i in range(8):
        m.add(feats, {"outcome": "win" if i < 6 else "loss", "symbol": "Y", "pnl": 50})
    nb = m.query(feats, k=8)
    wr = sum(1 for x in nb if x.get("outcome") == "win") / len(nb)
    assert wr >= 0.45                     # winning neighbourhood -> NO haircut (never invents)
