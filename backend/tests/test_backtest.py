import numpy as np
import pandas as pd

from aifos.backtest import monte_carlo, run_backtest, walk_forward
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


def test_monte_carlo_flags_small_and_all_win_samples():
    # 3 all-winning trades => must be flagged unreliable, never sold as an edge
    mc = monte_carlo([{"pnl_pct": 0.01}, {"pnl_pct": 0.02}, {"pnl_pct": 0.11}])
    assert mc["n_trades"] == 3 and mc["losses"] == 0
    assert mc["reliable"] is False
    assert "small sample" in mc["verdict"]
    # one dominant trade => fragility is surfaced
    assert mc["best_trade_share_of_gross_wins"] >= 0.5


def test_monte_carlo_reliable_with_enough_mixed_trades():
    rng = np.random.default_rng(3)
    trades = [{"pnl_pct": float(x)} for x in rng.normal(0.002, 0.03, 60)]
    mc = monte_carlo(trades)
    assert mc["reliable"] is True
    assert 0.0 <= mc["p_profit"] <= 1.0
    assert mc["p05_return"] <= mc["median_return"] <= mc["p95_return"]
