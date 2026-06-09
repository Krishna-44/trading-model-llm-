import pytest

from aifos.execution.base import Order, OrderSide
from aifos.execution.paper import BadQuoteError, PaperBroker


class FakeProvider:
    def __init__(self, px: float) -> None:
        self.px = px

    def latest_price(self, symbol: str, interval: str = "1d") -> float:
        return self.px

    def latest_quote(self, symbol: str) -> float:
        # mirror MarketDataProvider's default: the live-ish quote is the latest price
        return self.latest_price(symbol)


def test_long_then_close_realizes_pnl():
    b = PaperBroker(provider=FakeProvider(100), starting_cash=1_000_000,
                    commission_bps=0, slippage_bps=0)
    b.place_order(Order("X", OrderSide.BUY, 10))
    b.provider.px = 110
    fill = b.place_order(Order("X", OrderSide.SELL, 10))
    assert round(fill.realized_pnl, 2) == 100.0
    assert len(b.get_positions()) == 0  # flat
    assert round(b.get_account().cash, 2) == 1_000_100.0


def test_short_then_cover():
    b = PaperBroker(provider=FakeProvider(100), starting_cash=1_000_000,
                    commission_bps=0, slippage_bps=0)
    b.place_order(Order("X", OrderSide.SELL, 5))   # open short
    b.provider.px = 90
    fill = b.place_order(Order("X", OrderSide.BUY, 5))  # cover lower => profit
    assert round(fill.realized_pnl, 2) == 50.0


def test_average_price_on_add():
    b = PaperBroker(provider=FakeProvider(100), starting_cash=1_000_000,
                    commission_bps=0, slippage_bps=0)
    b.place_order(Order("X", OrderSide.BUY, 10))
    b.provider.px = 120
    b.place_order(Order("X", OrderSide.BUY, 10))
    pos = b.get_positions()[0]
    assert round(pos.avg_price, 2) == 110.0 and pos.qty == 20


def test_angelone_gate_blocks_when_off():
    import pytest

    from aifos.execution.base import LiveTradingDisabled
    from aifos.execution.live import AngelOneBroker
    # Live ORDERS are gated: with live_trading_enabled OFF (default), any real order
    # must be refused at the order gate — before any broker/SmartAPI session is touched
    # (so this stays offline and deterministic). Monitoring *reads* are intentionally
    # allowed once creds exist; it's real money movement the gate exists to block.
    with pytest.raises(LiveTradingDisabled):
        AngelOneBroker().place_order(Order("RELIANCE.NS", OrderSide.BUY, 1))


def test_angelone_symbol_mapping():
    from aifos.execution.live import AngelOneBroker
    assert AngelOneBroker()._angel_symbol("RELIANCE.NS") == ("RELIANCE-EQ", "NSE")


# ── bad-tick guard (regression for the EURINR 9197 blow-up) ──────────────────
def test_bad_tick_guard_refuses_corrupt_quote():
    """A corrupt quote ~92× the reference must be REFUSED — no fill, no state
    change. This is the exact failure that booked −4.13M on a single EURINR tick."""
    b = PaperBroker(provider=FakeProvider(110), starting_cash=1_000_000,
                    commission_bps=0, slippage_bps=0)
    b.place_order(Order("EURINR", OrderSide.SELL, 100))   # open short at ~110 (seeds reference)
    cash_before = b.cash
    n_before = len(b.get_positions())
    b.provider.px = 9197.03                                # corrupt tick (real rate ~110)
    with pytest.raises(BadQuoteError):
        b.place_order(Order("EURINR", OrderSide.BUY, 100))  # would have covered at garbage price
    # nothing changed: the bad print could not move cash or the position
    assert b.cash == cash_before
    assert len(b.get_positions()) == n_before


def test_bad_tick_guard_allows_legitimate_move_within_band():
    """A real move within the sanity band (here 4× < 5×) still fills normally —
    the guard rejects garbage, not volatility."""
    b = PaperBroker(provider=FakeProvider(100), starting_cash=1_000_000,
                    commission_bps=0, slippage_bps=0)
    b.place_order(Order("X", OrderSide.BUY, 10))
    b.provider.px = 400  # 4× — large but within the 5× band
    fill = b.place_order(Order("X", OrderSide.SELL, 10))
    assert round(fill.realized_pnl, 2) == 3000.0  # (400-100)*10


def test_bad_tick_guard_does_not_distort_marking():
    """A corrupt quote during mark-to-market must not poison equity (else the
    run-to-ruin guard reads a fake −10M and the curve is garbage). Falls back to
    the last good price."""
    b = PaperBroker(provider=FakeProvider(100), starting_cash=1_000_000,
                    commission_bps=0, slippage_bps=0)
    b.place_order(Order("X", OrderSide.SELL, 5))  # short at 100; cash += 500
    b.provider.px = 9197                          # corrupt tick
    eq = b.get_account().equity
    assert abs(eq - 1_000_000) < 1.0              # marked at last-good 100, not 9197


def test_quote_sanity_ratio_env_configurable(monkeypatch):
    monkeypatch.setenv("AIFOS_QUOTE_SANITY_MAX_RATIO", "2.0")
    b = PaperBroker(provider=FakeProvider(100), starting_cash=1_000_000,
                    commission_bps=0, slippage_bps=0)
    assert b.quote_sanity_ratio == 2.0
    b.place_order(Order("X", OrderSide.BUY, 1))   # seed ref at 100
    b.provider.px = 250                            # 2.5× — now outside the tightened 2× band
    with pytest.raises(BadQuoteError):
        b.place_order(Order("X", OrderSide.SELL, 1))
