"""Core market-data domain models and symbol classification."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class AssetClass(str, Enum):
    EQUITY = "equity"
    INDEX = "index"
    FOREX = "forex"
    CRYPTO = "crypto"
    UNKNOWN = "unknown"


class Candle(BaseModel):
    ts: str  # ISO timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


def classify_asset(symbol: str) -> AssetClass:
    """Infer asset class from yfinance symbol conventions.

    Used by the compliance agent (e.g. the FEMA offshore-forex guard) and by
    session/market-hours logic. Crypto trades 24/7; FX ~24/5; NSE has hours.
    """
    s = symbol.upper()
    if s.endswith("=X"):
        return AssetClass.FOREX
    if s.endswith("-USD") or s.endswith("-USDT") or s.endswith("-INR"):
        return AssetClass.CRYPTO
    if s.startswith("^"):
        return AssetClass.INDEX
    if s.endswith(".NS") or s.endswith(".BO"):
        return AssetClass.EQUITY
    return AssetClass.UNKNOWN


def is_offshore_forex(symbol: str) -> bool:
    """True for FX pairs that are NOT INR-quoted (the FEMA-sensitive ones).

    Indian residents may legally trade INR pairs on NSE/BSE currency
    derivatives; offshore spot FX (EURUSD, GBPUSD...) is FEMA-restricted.
    """
    if classify_asset(symbol) is not AssetClass.FOREX:
        return False
    return "INR" not in symbol.upper()
