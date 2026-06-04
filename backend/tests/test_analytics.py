from aifos.analytics import _equity_stats, _trade_stats, _window_pnl


def test_equity_stats_empty():
    s = _equity_stats([])
    assert s["points"] == 0 and s["sharpe"] == 0.0


def test_equity_stats_drawdown():
    curve = [{"equity": 100}, {"equity": 120}, {"equity": 90}, {"equity": 110}]
    s = _equity_stats(curve)
    assert s["points"] == 4 and s["max_drawdown"] < 0  # 120 -> 90 is a real DD


def test_trade_stats():
    trades = [{"realized_pnl": 100}, {"realized_pnl": -50}, {"realized_pnl": 200}]
    s = _trade_stats(trades)
    assert s["closed_trades"] == 3
    assert s["win_rate"] == round(2 / 3, 3)
    assert s["profit_factor"] == round(300 / 50, 3)


def test_window_pnl_empty():
    assert _window_pnl([], 7) == 0.0
