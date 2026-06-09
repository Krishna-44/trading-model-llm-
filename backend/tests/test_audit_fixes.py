"""Regressions for the engine audit findings (2026-06-09).

#1 monitor-only was bypassed by OANDA/Zerodha order paths + the deployment gate.
#3 the 'daily' loss kill switch never reset (start_new_day had no callers).
#2 a restart orphaned open positions' stops; manage_positions now synthesizes one.
"""
import numpy as np
import pandas as pd
import pytest

from aifos.config import settings
from aifos.deployment import live_execution_allowed
from aifos.execution.base import LiveTradingDisabled, Order, OrderSide
from aifos.execution.live import OANDABroker, ZerodhaBroker
from aifos.kernel import AIFOSKernel
from aifos.risk.engine import RiskEngine


# ── #1 monitor-only must block EVERY live order path ─────────────────────────
def test_monitor_only_blocks_oanda_and_zerodha_orders(monkeypatch):
    monkeypatch.setattr(settings, "live_trading_enabled", True)   # master switch ON
    monkeypatch.setattr(settings, "live_monitor_only", True)      # but monitor-only ON
    for broker_cls, sym in ((OANDABroker, "EURUSD=X"), (ZerodhaBroker, "RELIANCE.NS")):
        with pytest.raises(LiveTradingDisabled):
            broker_cls().place_order(Order(sym, OrderSide.BUY, 1))


def test_deployment_gate_blocks_on_monitor_only(monkeypatch):
    monkeypatch.setattr(settings, "live_monitor_only", True)
    ok, blocking = live_execution_allowed(readiness_ready=True)
    assert not ok
    assert any("monitor-only" in b for b in blocking)


# ── #3 daily-loss kill switch resets per IST day ─────────────────────────────
def test_risk_start_new_day_rescales_and_resets():
    r = RiskEngine()
    r.daily_pnl = -50_000.0
    r.realized_trades_today = 5
    r.start_new_day(2_000_000.0)
    assert r.daily_pnl == 0.0
    assert r.realized_trades_today == 0
    assert r.daily_start_equity == 2_000_000.0


def test_roll_risk_day_resets_on_new_day_and_is_idempotent():
    k = object.__new__(AIFOSKernel)
    k.risk = RiskEngine()
    k._risk_day = None

    class _Acct:
        equity = 1_500_000.0

    class _Broker:
        def get_account(self):
            return _Acct()

    k.broker = _Broker()
    k._roll_risk_day()                       # first call of the day
    assert k._risk_day is not None
    assert k.risk.daily_start_equity == 1_500_000.0
    k.risk.daily_pnl = -123.0
    k._roll_risk_day()                       # same day -> must NOT reset
    assert k.risk.daily_pnl == -123.0


# ── #2 orphaned position gets a synthesized default ATR stop ──────────────────
def test_synthesize_plan_builds_default_stop():
    idx = pd.date_range("2024-01-01", periods=60, freq="D")
    close = pd.Series(np.linspace(100, 160, 60), index=idx)
    df = pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99,
                       "close": close, "volume": 1e6}, index=idx)

    class _Prov:
        def history(self, sym, interval):
            return df

    class _Pos:
        symbol, qty, avg_price = "X", 10.0, 150.0

    k = object.__new__(AIFOSKernel)
    k.provider = _Prov()
    plan = k._synthesize_plan("X", _Pos())
    assert plan is not None
    assert plan["side"] == "long"
    assert plan["stop"] < 150.0 < plan["target"]   # long: stop below entry, target above
    assert plan["strategy"] == "(recovered)"


def test_synthesize_plan_short_position():
    idx = pd.date_range("2024-01-01", periods=60, freq="D")
    close = pd.Series(np.linspace(160, 100, 60), index=idx)
    df = pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99,
                       "close": close, "volume": 1e6}, index=idx)

    class _Prov:
        def history(self, sym, interval):
            return df

    class _Pos:
        symbol, qty, avg_price = "X", -10.0, 120.0

    k = object.__new__(AIFOSKernel)
    k.provider = _Prov()
    plan = k._synthesize_plan("X", _Pos())
    assert plan is not None and plan["side"] == "short"
    assert plan["target"] < 120.0 < plan["stop"]   # short: stop above entry, target below
