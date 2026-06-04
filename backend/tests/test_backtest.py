import numpy as np
import pandas as pd

from aifos.backtest import run_backtest, walk_forward
from aifos.strategies import build_strategy


def _df(n=320, seed=0):
    idx = pd.date_range("2020-01-01", periods=n)
    close = pd.Series(np.cumsum(np.random.default_rng(seed).normal(0.05, 1.0, n)) + 250,
                      index=idx).clip(lower=1)
    return pd.DataFrame({"open": close, "high": close + 1, "low": close - 1,
                         "close": close, "volume": 1e6}, index=idx)


def test_metrics_present():
    res = run_backtest(_df(), build_strategy("momentum"), interval="1d")
    for k in ("sharpe", "max_drawdown", "total_return", "num_trades", "win_rate"):
        assert k in res.metrics
    assert len(res.equity_curve) == 320
    # max drawdown is a loss => non-positive
    assert res.metrics["max_drawdown"] <= 0


def test_no_lookahead_positions_lagged():
    # positions must be shifted: first bar can never carry exposure
    res = run_backtest(_df(), build_strategy("momentum"), interval="1d")
    assert res.positions.iloc[0] == 0.0


def test_walk_forward_runs():
    wf = walk_forward(_df(400), build_strategy("mean_reversion"), interval="1d")
    assert "oos" in wf and isinstance(wf["folds"], list)
