"""Broker abstraction. One interface; paper and live implementations behind it.

``LiveTradingDisabled`` is raised by every live adapter unless the operator has
explicitly set ``AIFOS_LIVE_TRADING_ENABLED=true`` AND supplied credentials.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import Enum


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class LiveTradingDisabled(RuntimeError):
    """Raised when a real-money action is attempted while the gate is closed."""


@dataclass
class Order:
    symbol: str
    side: OrderSide
    qty: float
    type: OrderType = OrderType.MARKET
    limit_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    client_id: str = ""
    meta: dict = field(default_factory=dict)


@dataclass
class Fill:
    order_id: str
    symbol: str
    side: OrderSide
    qty: float
    price: float
    ts: str
    commission: float = 0.0
    slippage: float = 0.0
    realized_pnl: float = 0.0
    status: str = "filled"

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id, "symbol": self.symbol, "side": self.side.value,
            "qty": round(self.qty, 6), "price": round(self.price, 4), "ts": self.ts,
            "commission": round(self.commission, 2), "slippage": round(self.slippage, 4),
            "realized_pnl": round(self.realized_pnl, 2), "status": self.status,
        }


@dataclass
class Position:
    symbol: str
    qty: float  # signed: + long, - short
    avg_price: float
    market_price: float = 0.0

    @property
    def market_value(self) -> float:
        return self.qty * self.market_price

    @property
    def unrealized_pnl(self) -> float:
        return self.qty * (self.market_price - self.avg_price)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol, "qty": round(self.qty, 6),
            "avg_price": round(self.avg_price, 4),
            "market_price": round(self.market_price, 4),
            "market_value": round(self.market_value, 2),
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "side": "long" if self.qty > 0 else "short" if self.qty < 0 else "flat",
        }


@dataclass
class Account:
    cash: float
    equity: float
    currency: str = "INR"
    realized_pnl: float = 0.0

    def to_dict(self) -> dict:
        return {
            "cash": round(self.cash, 2), "equity": round(self.equity, 2),
            "currency": self.currency, "realized_pnl": round(self.realized_pnl, 2),
        }


class BrokerAdapter(abc.ABC):
    name: str = "base"
    is_live: bool = False

    @abc.abstractmethod
    def connect(self) -> None: ...

    @abc.abstractmethod
    def get_account(self) -> Account: ...

    @abc.abstractmethod
    def get_positions(self) -> list[Position]: ...

    @abc.abstractmethod
    def get_price(self, symbol: str) -> float: ...

    @abc.abstractmethod
    def place_order(self, order: Order) -> Fill: ...

    @abc.abstractmethod
    def close_position(self, symbol: str) -> Fill | None: ...
