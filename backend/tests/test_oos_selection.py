"""OOS-aware strategy selection (governance.StrategyEvolutionAgent).

Regression for the in-sample-selection flaw found by the edge-attribution study: the
agent used to rank strategies by a single in-sample backtest Sharpe, which preferred
cost-fragile high-trade-count losers (vwap_trend) and noise (heikin_trend) over the
genuine cost-surviving OOS edge (ema_trend_fib). The fix ranks by OOS Sharpe with
explicit robustness penalties (net loser, cost-fragile, one-trade-dependent), memoized
per bar. It is a pure SELECTION reweight — it fabricates no signal and sizes nothing.
"""
from types import SimpleNamespace

import pandas as pd

import aifos.agents.governance as gov

# name -> (oos_sharpe, total_return, survives_2x_cost, return_without_best_trade)
SCEN = {
    "ema_trend_fib":  dict(sharpe=0.6, total_return=0.5, cost_ok=True,  rwb=0.3),   # clean robust -> 0.60
    "vwap_trend":     dict(sharpe=0.5, total_return=0.4, cost_ok=False, rwb=0.2),   # cost-fragile -> 0.50-0.6 = -0.10
    "mean_reversion": dict(sharpe=0.3, total_return=-0.1, cost_ok=True, rwb=0.1),   # net loser   -> 0.30-1.0 = -0.70
}


class _Res:
    def __init__(self, name: str) -> None:
        self.metrics = {"total_return": SCEN[name]["total_return"]}
        self.trades = name  # carried through to the monte_carlo stub


def _stub(monkeypatch, wf_counter=None):
    def fake_wf(df, strat, interval="1d"):
        if wf_counter is not None:
            wf_counter["n"] += 1
        return {"oos": {"sharpe": SCEN[strat.name]["sharpe"]}}
    monkeypatch.setattr(gov, "walk_forward", fake_wf)
    monkeypatch.setattr(gov, "run_backtest", lambda df, strat, interval="1d": _Res(strat.name))
    monkeypatch.setattr(gov, "cost_stress",
                        lambda df, strat, interval="1d": {"survives_2x_cost": SCEN[strat.name]["cost_ok"]})
    monkeypatch.setattr(gov, "monte_carlo",
                        lambda trades: {"return_without_best_trade": SCEN[trades]["rwb"]})
    monkeypatch.setattr(gov, "is_enabled", lambda n: n in SCEN)


def _ctx(periods=5, symbol="BTC-USD", interval="1d"):
    idx = pd.date_range("2024-01-01", periods=periods, freq="D")
    df = pd.DataFrame({"close": range(100, 100 + periods)}, index=idx)
    return SimpleNamespace(df=df, symbol=symbol, extra={"interval": interval})


def test_oos_selection_prefers_robust_edge_over_costfragile_and_loser(monkeypatch):
    gov._SEL_CACHE.clear()
    _stub(monkeypatch)
    ctx = _ctx()
    op = gov.StrategyEvolutionAgent().analyze(ctx)
    # the robust, cost-surviving OOS edge wins — not the cost-fragile or the loser
    assert ctx.extra["strategy_name"] == "ema_trend_fib"
    sc = op.signals["scores"]
    assert sc["ema_trend_fib"] == 0.6           # clean: raw OOS sharpe
    assert sc["vwap_trend"] == -0.1             # -0.6 cost-fragility penalty
    assert sc["mean_reversion"] == -0.7         # -1.0 net-loser penalty


def test_selection_is_memoized_per_bar(monkeypatch):
    gov._SEL_CACHE.clear()
    calls = {"n": 0}
    _stub(monkeypatch, wf_counter=calls)
    agent = gov.StrategyEvolutionAgent()
    ctx = _ctx(periods=5)
    agent.analyze(ctx)
    assert calls["n"] == 3                       # one walk_forward per enabled strategy
    agent.analyze(ctx)                           # same bar -> served from cache
    assert calls["n"] == 3
    agent.analyze(_ctx(periods=6))               # a new bar closed -> recompute
    assert calls["n"] == 6


def test_fallback_is_real_edge_default_not_momentum(monkeypatch):
    gov._SEL_CACHE.clear()
    _stub(monkeypatch)
    monkeypatch.setattr(gov, "is_enabled", lambda n: False)  # nothing enabled -> empty scores
    ctx = _ctx(symbol="UNKNOWN")
    gov.StrategyEvolutionAgent().analyze(ctx)
    assert ctx.extra["strategy_name"] == "ema_trend_fib"     # never the in-sample 'momentum'
