"""Directional-balance / portfolio-heat gate tests.

Regression for the marathon going 100% short. The gate caps the book's NET
long-vs-short imbalance, blocks ONLY additions to the over-cap dominant side,
and always allows trades that reduce the imbalance.
"""
from aifos.risk.portfolio_heat import check

EQ = 1_000_000.0


def test_empty_book_allows_first_trade():
    r = check("short", 100_000, [], EQ)
    assert not r.blocked


def test_below_cap_allows_another_same_side():
    book = [{"dir": -1, "notional": 300_000}]  # 30% net short
    r = check("short", 100_000, book, EQ)       # -> 40% < 45% cap
    assert not r.blocked


def test_over_cap_blocks_adding_to_dominant_side():
    book = [{"dir": -1, "notional": 400_000}]  # 40% net short
    r = check("short", 100_000, book, EQ)       # -> 50% > 45% cap, same side
    assert r.blocked and "short" in r.reason


def test_over_cap_allows_opposite_side_that_reduces_imbalance():
    book = [{"dir": -1, "notional": 500_000}]  # 50% net short (already over)
    r = check("long", 100_000, book, EQ)        # long REDUCES the short skew
    assert not r.blocked


def test_mixed_book_uses_net_not_gross():
    # 50% short + 20% long => net 30% short; a 10% short -> net 40% < 45% -> allowed
    book = [{"dir": -1, "notional": 500_000}, {"dir": 1, "notional": 200_000}]
    r = check("short", 100_000, book, EQ)
    assert not r.blocked


def test_custom_cap_is_respected():
    book = [{"dir": 1, "notional": 250_000}]   # 25% net long
    r = check("long", 10_000, book, EQ, max_imbalance_pct=0.20)  # -> 26% > 20%
    assert r.blocked and "long" in r.reason


def test_non_trade_side_or_zero_notional_never_blocks():
    assert not check("hold", 100_000, [], EQ).blocked
    assert not check("short", 0.0, [], EQ).blocked
    assert not check("short", 100_000, [], 0.0).blocked  # no equity -> can't judge


def test_result_reports_signed_imbalance_and_gross_heat():
    book = [{"dir": -1, "notional": 200_000}]
    r = check("short", 100_000, book, EQ)
    assert round(r.net_imbalance_pct, 2) == -0.30  # net 30% short (signed)
    assert round(r.gross_heat_pct, 2) == 0.30
