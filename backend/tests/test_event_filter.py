"""Tests for risk.event_filter — verify the calendar gate behavior."""
from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from aifos.risk.event_filter import is_blocked, INDIA_RBI_2026

IST = ZoneInfo("Asia/Kolkata")


def _ist(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=IST)


def test_open_auction_window_blocks():
    # Tuesday 9:18 IST is inside the 9:15-9:20 open auction window.
    now = _ist(2026, 6, 9, 9, 18)
    r = is_blocked("RELIANCE.NS", now=now)
    assert r.blocked is True
    assert "open" in r.label.lower()


def test_closing_auction_window_blocks():
    # Tuesday 15:28 IST is in the closing auction 15:25-15:30.
    now = _ist(2026, 6, 9, 15, 28)
    r = is_blocked("RELIANCE.NS", now=now)
    assert r.blocked is True
    assert "clos" in r.label.lower()


def test_thursday_expiry_tail_blocks():
    # Thursday 14:30 IST is in the NSE weekly expiry window 14:00-15:30.
    # 2026-06-11 is a Thursday.
    now = _ist(2026, 6, 11, 14, 30)
    r = is_blocked("NIFTY.NS", now=now)
    assert r.blocked is True
    assert "expiry" in r.label.lower()


def test_thursday_morning_allows():
    # Thursday 11:00 IST — outside both auctions and expiry tail.
    now = _ist(2026, 6, 11, 11, 0)
    r = is_blocked("NIFTY.NS", now=now)
    assert r.blocked is False


def test_rbi_policy_day_blocks_morning():
    # 2026-06-05 is an RBI MPC date. 10:30 IST should be blocked.
    now = _ist(2026, 6, 5, 10, 30)
    r = is_blocked("HDFCBANK.NS", now=now)
    assert r.blocked is True
    assert "rbi" in r.label.lower()


def test_rbi_policy_day_allows_evening():
    # Same RBI day, 15:00 IST — outside the 09:00-14:00 block window.
    now = _ist(2026, 6, 5, 15, 0)
    r = is_blocked("HDFCBANK.NS", now=now)
    # Note: 15:00 is also inside the closing auction (15:25-15:30) but 15:00 isn't.
    assert r.blocked is False


def test_unknown_symbol_handled_gracefully():
    now = _ist(2026, 6, 9, 11, 0)
    r = is_blocked("SOMETHING.WEIRD", now=now)
    # Should not crash; mid-day allows.
    assert r.blocked is False
