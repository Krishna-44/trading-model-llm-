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


def _has_creds(name: str) -> bool:
    s = settings
    if name == "angelone":
        return bool(s.angelone_api_key and s.angelone_client_code
                    and s.angelone_pin and s.angelone_totp_secret)
    if name == "zerodha":
        return bool(s.zerodha_api_key and s.zerodha_access_token)
    if name == "oanda":
        return bool(s.oanda_api_token and s.oanda_account_id)
    return False


def get_broker(name: str | None = None, **paper_kwargs) -> BrokerAdapter:
    name = (name or settings.broker).lower()
    if name == "paper":
        return PaperBroker(**paper_kwargs)
    if name in _LIVE:
        # A live broker activates for MONITORING as soon as credentials exist — it can
        # READ the real account regardless of the trading gate. Real ORDERS stay blocked
        # inside the adapter (live_trading_enabled + monitor_only + readiness).
        if settings.live_trading_enabled or _has_creds(name):
            armed = settings.live_trading_enabled and not settings.live_monitor_only
            logger.warning("broker '%s' active — %s", name,
                           "LIVE ORDERS ARMED" if armed else "MONITOR-ONLY (read-only)")
            return _LIVE[name]()
        logger.warning("broker '%s' selected but no credentials and live off — PAPER fallback. "
                       "Set the broker's creds in .env to monitor your real account.", name)
        return PaperBroker(**paper_kwargs)
    raise ValueError(f"unknown broker '{name}'")
