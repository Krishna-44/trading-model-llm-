"""Marathon safety: persistent run-to-ruin halt + min-hold churn guard.

Both regressions trace to the -4.14M blow-up: the in-memory ruin-stop was
re-armed by MARATHON_ON_START on every restart, and the committee flip-flopped
a symbol in/out every cycle bleeding commissions.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from aifos.config import settings
from aifos.kernel import AIFOSKernel


def _bare_kernel() -> AIFOSKernel:
    """An AIFOSKernel WITHOUT the heavy __init__ (no DB/broker connect) — just
    enough state to unit-test the pure flag/gate methods."""
    k = object.__new__(AIFOSKernel)
    k._last_trade_ts = {}
    return k


def _decision(side: str) -> SimpleNamespace:
    return SimpleNamespace(side=side)


# ── persistent run-to-ruin halt ──────────────────────────────────────────────
def test_marathon_halt_flag_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_cache_dir", str(tmp_path))
    k = _bare_kernel()
    assert not k.marathon_halted()
    k._set_marathon_halted(True)
    assert k.marathon_halted()
    assert (tmp_path / "marathon_halted.flag").exists()
    k._set_marathon_halted(False)
    assert not k.marathon_halted()


def test_marathon_halt_survives_restart(tmp_path, monkeypatch):
    """A fresh kernel object (simulating a process restart) still sees the halt —
    this is what stops KeepAlive + MARATHON_ON_START from re-arming a wiped book."""
    monkeypatch.setattr(settings, "data_cache_dir", str(tmp_path))
    _bare_kernel()._set_marathon_halted(True)
    assert _bare_kernel().marathon_halted()


# ── min-hold churn guard ─────────────────────────────────────────────────────
def test_min_hold_blocks_recent_reentry(monkeypatch):
    monkeypatch.setattr(settings, "min_hold_seconds", 900)
    k = _bare_kernel()
    k._last_trade_ts["EURINR=X"] = datetime.now(timezone.utc) - timedelta(seconds=120)
    r = k._min_hold_gate("EURINR=X", _decision("short"))
    assert r is not None and "min-hold" in r


def test_min_hold_allows_after_window(monkeypatch):
    monkeypatch.setattr(settings, "min_hold_seconds", 900)
    k = _bare_kernel()
    k._last_trade_ts["X"] = datetime.now(timezone.utc) - timedelta(seconds=1200)
    assert k._min_hold_gate("X", _decision("long")) is None


def test_min_hold_allows_first_ever_trade(monkeypatch):
    monkeypatch.setattr(settings, "min_hold_seconds", 900)
    assert _bare_kernel()._min_hold_gate("FRESH", _decision("long")) is None


def test_min_hold_ignores_non_trade_side(monkeypatch):
    monkeypatch.setattr(settings, "min_hold_seconds", 900)
    k = _bare_kernel()
    k._last_trade_ts["X"] = datetime.now(timezone.utc)
    assert k._min_hold_gate("X", _decision("hold")) is None


def test_min_hold_disabled_when_zero(monkeypatch):
    monkeypatch.setattr(settings, "min_hold_seconds", 0)
    k = _bare_kernel()
    k._last_trade_ts["X"] = datetime.now(timezone.utc)
    assert k._min_hold_gate("X", _decision("short")) is None
