"""Market-session awareness — which markets are open right now.

The autonomous engine uses this to ROTATE: trade NSE in Indian hours, forex when
FX is open, crypto 24/7 — and never trade a closed market on stale data. Hours are
approximations of the real sessions (no exchange-holiday calendar), good enough to
gate trading and honest about it.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from .config import settings
from .data.models import AssetClass, classify_asset

IST = timezone(timedelta(hours=5, minutes=30))


def _now(now: datetime | None = None) -> datetime:
    return now or datetime.now(timezone.utc)


def nse_state(now: datetime) -> str:
    """NSE status: open | after-hours | weekend | holiday."""
    ist = now.astimezone(IST)
    if ist.weekday() >= 5:
        return "weekend"
    if ist.date().isoformat() in set(settings.nse_holidays):
        return "holiday"
    if time(9, 15) <= ist.time() <= time(15, 30):
        return "open"
    return "after-hours"


def is_market_open(symbol: str, now: datetime | None = None) -> bool:
    """True if the instrument's market is currently in session."""
    now = _now(now)
    cls = classify_asset(symbol)
    if cls is AssetClass.CRYPTO:
        return True  # 24/7
    if cls is AssetClass.FOREX:
        wd = now.weekday()  # Mon=0 .. Sun=6  (UTC)
        if wd == 5:                       # Saturday — closed
            return False
        if wd == 6:                       # Sunday — opens ~21:00 UTC (Sydney)
            return now.hour >= 21
        if wd == 4:                       # Friday — closes ~21:00 UTC
            return now.hour < 21
        return True                       # Mon–Thu — open
    if cls in (AssetClass.EQUITY, AssetClass.INDEX):
        return nse_state(now) == "open"   # Mon–Fri 09:15–15:30 IST, excluding NSE holidays
    return False


def _forex_sessions(now: datetime) -> list[str]:
    """Active forex centres (UTC): Asia ~21–09, London ~07–16, New York ~12–21."""
    h = now.hour
    s = []
    if h >= 21 or h < 9:
        s.append("Asia")
    if 7 <= h < 16:
        s.append("London")
    if 12 <= h < 21:
        s.append("New York")
    return s


def session_status(universe: list[str], now: datetime | None = None) -> dict:
    now = _now(now)
    ist = now.astimezone(IST)
    open_syms = [s for s in universe if is_market_open(s, now)]
    by_class: dict[str, list[str]] = {}
    for s in open_syms:
        by_class.setdefault(classify_asset(s).value, []).append(s)

    nse_st = nse_state(now)
    nse_open = nse_st == "open"
    forex_open = bool(by_class.get("forex"))
    fx = _forex_sessions(now) if forex_open else []

    if nse_open:
        focus = "NSE — Indian equities, indices & option-chain (intraday)"
    elif forex_open:
        focus = f"Forex — {', '.join(fx) or 'between centres'} + crypto"
    elif by_class.get("crypto"):
        focus = "Crypto only — NSE & forex closed (weekend / off-hours)"
    else:
        focus = "All major markets closed — monitoring only"

    return {
        "now_utc": now.isoformat(),
        "now_ist": ist.strftime("%a %H:%M IST"),
        "nse_open": nse_open,
        "nse_state": nse_st,
        "forex_open": forex_open,
        "crypto_open": True,
        "forex_sessions": fx,
        "open_symbols": open_syms,
        "open_by_class": {k: len(v) for k, v in by_class.items()},
        "tradeable_count": len(open_syms),
        "focus": focus,
        "note": "The engine trades only open markets (rotates NSE→forex→crypto); a closed "
                "market is monitored, not traded, so fills stay realistic.",
    }
