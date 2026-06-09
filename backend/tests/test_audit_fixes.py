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


import math


# ── #4 equity sizes in WHOLE shares so paper matches live execution ──────────
def test_equity_sizing_floors_to_whole_shares():
    a = RiskEngine().assess(side="long", entry=100.0, atr=2.0, confidence=0.9,
                            equity=1_000_000, open_positions=0,
                            current_exposure_value=0, asset_class="equity")
    assert a.approved
    assert a.size_units == math.floor(a.size_units) and a.size_units >= 1  # whole shares


def test_equity_rejects_sub_one_share():
    # a very high-priced share vs small equity -> sizes to <1 share -> refused
    a = RiskEngine().assess(side="long", entry=5_000_000.0, atr=100_000.0, confidence=0.9,
                            equity=100_000, open_positions=0,
                            current_exposure_value=0, asset_class="equity")
    assert not a.approved
    assert any("whole share" in r for r in a.rejections)


def test_crypto_keeps_fractional_sizing():
    # BTC-like price: the position cap forces a sub-1 fractional size, which is
    # legitimate on a crypto venue and must NOT be floored away.
    a = RiskEngine().assess(side="long", entry=63_000.0, atr=1_500.0, confidence=0.9,
                            equity=1_000_000, open_positions=0,
                            current_exposure_value=0, asset_class="crypto")
    assert a.approved
    assert a.size_units != math.floor(a.size_units)  # fractional preserved


# ── #5 live fills record the broker price, never a synthetic one ─────────────
def test_live_fill_prefers_broker_price():
    from aifos.execution.live import _resolve_live_fill_price
    assert _resolve_live_fill_price(101.5, 100.0, False) == (101.5, "filled")


def test_live_fill_uses_real_quote_when_no_broker_price():
    from aifos.execution.live import _resolve_live_fill_price
    assert _resolve_live_fill_price(0.0, 100.0, False) == (100.0, "filled")


def test_live_fill_refuses_synthetic_quote():
    from aifos.execution.live import _resolve_live_fill_price
    price, status = _resolve_live_fill_price(0.0, 100.0, True)  # feed is synthetic
    assert price == 0.0 and status == "price-unverified"  # never fabricate a fill price


def test_live_fill_unverified_when_no_price():
    from aifos.execution.live import _resolve_live_fill_price
    assert _resolve_live_fill_price(0.0, 0.0, False) == (0.0, "price-unverified")


def test_provider_tracks_synthetic_source(monkeypatch):
    from aifos.data.providers import YFinanceProvider
    p = YFinanceProvider()
    assert p.last_source("NEVERSEEN_XYZ") == "unknown"
    monkeypatch.setattr(p, "_fetch_yf", lambda *a, **k: None)   # force feed failure
    monkeypatch.setattr(p, "_read_cache", lambda key: None)
    monkeypatch.setattr(p, "_write_cache", lambda key, df: None)
    p.history("FAKE_SYNTH_SYM", "1d")
    assert p.last_source("FAKE_SYNTH_SYM") == "synthetic"


# ── #6 kill switch must NOT freeze position exits ────────────────────────────
def test_run_universe_manage_only_runs_exits_skips_entries():
    """manage_only (kill switch active) must still run manage_positions (exits) but
    open NO new positions (no tick() entries)."""
    k = object.__new__(AIFOSKernel)
    calls = {"manage": 0, "tick": 0}
    k._roll_risk_day = lambda: None
    k.tradeable_now = lambda: ["AAA", "BBB"]
    k.manage_positions = lambda: calls.__setitem__("manage", calls["manage"] + 1)

    def _tick(sym, interval, execute=True):
        calls["tick"] += 1
        dec = type("D", (), {"action": "HOLD", "confidence": 0.0, "executed": False})()
        return dec, None

    k.tick = _tick
    k.snapshot_equity = lambda: 0.0
    k.risk = type("R", (), {"marathon": False})()
    k._save_broker_state = lambda: None
    k._check_readiness_alert = lambda: None
    k._cook_step = lambda: None

    k.run_universe(execute=True, open_only=True, manage_only=True)
    assert calls["manage"] == 1 and calls["tick"] == 0   # exits ran, no new entries

    k.run_universe(execute=True, open_only=True, manage_only=False)
    assert calls["manage"] == 2 and calls["tick"] == 2   # exits + entries on both symbols


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
