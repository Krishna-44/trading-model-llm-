"""NSE option-chain feed — real public data, honest about availability.

NSE's API needs browser-like headers and a primed cookie; it can also rate-limit
or block. Every failure returns ``{"available": False, "reason": ...}`` so the
rest of the system degrades gracefully instead of inventing data.
"""
from __future__ import annotations

import logging
import time

import requests

logger = logging.getLogger("aifos.data.options")

_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/option-chain",
}

_INDEX = {"^NSEI": "NIFTY", "^NSEBANK": "BANKNIFTY", "NIFTY": "NIFTY", "BANKNIFTY": "BANKNIFTY"}

_session: requests.Session | None = None
_cache: dict[str, tuple[float, dict]] = {}
_TTL = 90.0  # seconds — NSE updates OI slowly; protects against rate limits


def nse_symbol(symbol: str) -> tuple[str | None, str | None]:
    """Map an AIFOS symbol to (nse_symbol, kind) or (None, None) if no NSE options."""
    if symbol in _INDEX:
        return _INDEX[symbol], "index"
    if symbol.endswith(".NS"):
        return symbol[:-3], "equity"
    return None, None


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        s = requests.Session()
        s.headers.update(_HEADERS)
        try:  # prime cookies the way a browser would
            s.get("https://www.nseindia.com/option-chain", timeout=8)
        except Exception:  # noqa: BLE001
            pass
        _session = s
    return _session


def fetch_option_chain(symbol: str, ttl: float = _TTL) -> dict:
    nsym, kind = nse_symbol(symbol)
    if not nsym:
        return {"available": False, "reason": f"{symbol} has no NSE-listed options"}

    hit = _cache.get(nsym)
    if hit and (time.time() - hit[0]) < ttl:
        return hit[1]

    base = ("https://www.nseindia.com/api/option-chain-indices?symbol="
            if kind == "index" else
            "https://www.nseindia.com/api/option-chain-equities?symbol=")
    url = base + nsym
    try:
        sess = _get_session()
        r = sess.get(url, timeout=10)
        if r.status_code == 401:  # cookie expired — re-prime once
            sess.get("https://www.nseindia.com/option-chain", timeout=8)
            r = sess.get(url, timeout=10)
        if r.status_code != 200:
            out = {"available": False, "reason": f"NSE returned HTTP {r.status_code}"}
        else:
            data = r.json()
            if not (data.get("records") or {}).get("data"):
                out = {"available": False,
                       "reason": "NSE served an empty chain (public feed blocked for automated access)"}
            else:
                out = {"available": True, "nse_symbol": nsym, "kind": kind, "raw": data}
    except Exception as exc:  # noqa: BLE001
        out = {"available": False, "reason": f"NSE feed unreachable: {exc}"}

    _cache[nsym] = (time.time(), out)  # cache failures too, so polling won't hammer NSE
    return out
