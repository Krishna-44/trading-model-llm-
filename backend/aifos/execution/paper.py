"""Fully-functional paper broker: realistic fills with slippage + commission,
signed positions, correct realized-PnL accounting on reduce/flip. This is the
DEFAULT execution venue and the one used to validate the system before any
real money is ever connected."""
from __future__ import annotations

import logging
from itertools import count

from ..config import settings
from ..data.providers import MarketDataProvider, get_provider
from .base import Account, BrokerAdapter, Fill, Order, OrderSide, Position

logger = logging.getLogger("aifos.exec.paper")


class PaperBroker(BrokerAdapter):
    name = "paper"
    is_live = False

    def __init__(
        self, provider: MarketDataProvider | None = None,
        starting_cash: float | None = None,
        commission_bps: float = 3.0, slippage_bps: float = 2.0,
    ) -> None:
        self.provider = provider or get_provider()
        self.cash = starting_cash if starting_cash is not None else settings.starting_capital
        self.commission_bps = commission_bps
        self.slippage_bps = slippage_bps
        self.positions: dict[str, Position] = {}
        self.realized_pnl = 0.0
        self._oid = count(1)
        self._last_prices: dict[str, float] = {}

    def connect(self) -> None:
        logger.info("paper broker ready: cash=%.2f %s", self.cash, settings.base_currency)

    def reset(self, starting_cash: float | None = None) -> None:
        """Restore the book to its starting state — for a fresh forward test."""
        self.cash = starting_cash if starting_cash is not None else settings.starting_capital
        self.positions.clear()
        self.realized_pnl = 0.0
        self._last_prices.clear()
        logger.info("paper broker reset: cash=%.2f %s", self.cash, settings.base_currency)

    # --- pricing ---------------------------------------------------------
    def get_price(self, symbol: str) -> float:
        price = self.provider.latest_price(symbol)
        self._last_prices[symbol] = price
        return price

    def mark_to_market(self, prices: dict[str, float] | None = None) -> None:
        for sym, pos in self.positions.items():
            px = (prices or {}).get(sym) or self._last_prices.get(sym)
            if px is None:
                try:
                    px = self.get_price(sym)
                except Exception:  # noqa: BLE001
                    px = pos.avg_price
            pos.market_price = px

    # --- account ---------------------------------------------------------
    def get_account(self) -> Account:
        self.mark_to_market()
        equity = self.cash + sum(p.market_value for p in self.positions.values())
        return Account(cash=self.cash, equity=equity,
                       currency=settings.base_currency, realized_pnl=self.realized_pnl)

    def get_positions(self) -> list[Position]:
        self.mark_to_market()
        return [p for p in self.positions.values() if abs(p.qty) > 1e-9]

    # --- execution -------------------------------------------------------
    def place_order(self, order: Order) -> Fill:
        from ..data.providers import YFinanceProvider  # noqa: F401 (clarity)

        ref = self.get_price(order.symbol)
        direction = 1 if order.side is OrderSide.BUY else -1
        slip = ref * (self.slippage_bps / 1e4) * direction
        fill_price = ref + slip
        signed_qty = direction * abs(order.qty)
        commission = abs(signed_qty) * fill_price * (self.commission_bps / 1e4)

        realized = self._apply_fill(order.symbol, signed_qty, fill_price)
        self.cash -= signed_qty * fill_price       # buy lowers cash, sell raises it
        self.cash -= commission
        self.realized_pnl += realized

        fill = Fill(
            order_id=f"PAPER-{next(self._oid)}", symbol=order.symbol, side=order.side,
            qty=abs(order.qty), price=fill_price, ts=_now_iso(),
            commission=commission, slippage=abs(slip), realized_pnl=realized,
        )
        logger.info("paper fill %s %s %.4f @ %.4f (rpnl=%.2f)",
                    order.side.value, order.symbol, order.qty, fill_price, realized)
        return fill

    def close_position(self, symbol: str) -> Fill | None:
        pos = self.positions.get(symbol)
        if not pos or abs(pos.qty) < 1e-9:
            return None
        side = OrderSide.SELL if pos.qty > 0 else OrderSide.BUY
        return self.place_order(Order(symbol=symbol, side=side, qty=abs(pos.qty)))

    def _apply_fill(self, symbol: str, signed_qty: float, price: float) -> float:
        """Update position, return realized PnL from any reduced/closed quantity."""
        pos = self.positions.get(symbol)
        if pos is None or abs(pos.qty) < 1e-9:
            self.positions[symbol] = Position(symbol, signed_qty, price, price)
            return 0.0

        realized = 0.0
        same_dir = (pos.qty > 0) == (signed_qty > 0)
        if same_dir:
            new_qty = pos.qty + signed_qty
            pos.avg_price = (pos.avg_price * pos.qty + price * signed_qty) / new_qty
            pos.qty = new_qty
        else:
            closing = min(abs(signed_qty), abs(pos.qty))
            # realized on the closed units (long: price-avg; short: avg-price)
            realized = closing * (price - pos.avg_price) * (1 if pos.qty > 0 else -1)
            new_qty = pos.qty + signed_qty
            if abs(new_qty) < 1e-9:
                pos.qty = 0.0
            elif (new_qty > 0) == (pos.qty > 0):
                pos.qty = new_qty  # partial close, avg unchanged
            else:
                pos.qty, pos.avg_price = new_qty, price  # flipped — remainder at fill
        pos.market_price = price
        return realized


def _now_iso() -> str:
    # imported here to keep module import cheap and avoid global Date usage
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
