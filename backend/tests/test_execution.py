from aifos.execution.base import Order, OrderSide
from aifos.execution.paper import PaperBroker


class FakeProvider:
    def __init__(self, px: float) -> None:
        self.px = px

    def latest_price(self, symbol: str, interval: str = "1d") -> float:
        return self.px


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
    # gate defaults OFF -> any connection attempt must be refused
    with pytest.raises(LiveTradingDisabled):
        AngelOneBroker().connect()


def test_angelone_symbol_mapping():
    from aifos.execution.live import AngelOneBroker
    assert AngelOneBroker()._angel_symbol("RELIANCE.NS") == ("RELIANCE-EQ", "NSE")
