"""Broker factory. Defaults to paper. Live brokers are constructed but remain
inert until the gate is opened + credentials are present (enforced in adapters)."""
from __future__ import annotations

import logging

from ..config import settings
from .base import BrokerAdapter
from .live import AngelOneBroker, OANDABroker, UpstoxBroker, ZerodhaBroker
from .paper import PaperBroker

logger = logging.getLogger("aifos.exec")

_LIVE = {
    "zerodha": ZerodhaBroker,
    "oanda": OANDABroker,
    "upstox": UpstoxBroker,
    "angelone": AngelOneBroker,
}


def get_broker(name: str | None = None, **paper_kwargs) -> BrokerAdapter:
    name = (name or settings.broker).lower()
    if name == "paper":
        return PaperBroker(**paper_kwargs)
    if name in _LIVE:
        if not settings.live_trading_enabled:
            logger.warning(
                "broker '%s' selected but LIVE TRADING is OFF — falling back to PAPER. "
                "Set AIFOS_LIVE_TRADING_ENABLED=true to arm it.", name
            )
            return PaperBroker(**paper_kwargs)
        logger.warning("⚠ ARMING LIVE BROKER '%s' — real orders enabled", name)
        return _LIVE[name]()
    raise ValueError(f"unknown broker '{name}'")
