"""Fundamentals & valuation research.

Pulls company fundamentals and turns them into a quality score, a value score,
and a stance the Fundamentals agent can vote with. Source priority:
  1. OpenBB SDK (`openbb`) if installed — standardized, multi-provider.
  2. yfinance `.get_info()` — free, keyless, works for NSE equities today.
Only meaningful for equities; everything else returns ``applicable=False`` so
the agent abstains (weight 0) and the core decision is unchanged.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from ..data.models import AssetClass, classify_asset

logger = logging.getLogger("aifos.research")
_TTL = 6 * 3600  # fundamentals move slowly; cache hard


@dataclass
class Fundamentals:
    symbol: str
    applicable: bool
    source: str = "none"
    name: str = ""
    sector: str = ""
    metrics: dict = field(default_factory=dict)      # normalized raw values
    quality_score: float = 0.0                       # 0..1
    value_score: float = 0.0                         # 0..1
    composite: float = 0.5                           # 0..1
    stance: str = "neutral"
    confidence: float = 0.0
    reasoning: str = ""

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol, "applicable": self.applicable, "source": self.source,
            "name": self.name, "sector": self.sector, "metrics": self.metrics,
            "quality_score": round(self.quality_score, 3),
            "value_score": round(self.value_score, 3),
            "composite": round(self.composite, 3), "stance": self.stance,
            "confidence": round(self.confidence, 3), "reasoning": self.reasoning,
        }


def _avg(vals: list[float | None]) -> float | None:
    xs = [v for v in vals if v is not None]
    return sum(xs) / len(xs) if xs else None


def _quality(roe, margin, growth, de) -> float | None:
    comps: list[float | None] = []
    if roe is not None:
        comps.append(1.0 if roe >= 0.18 else 0.7 if roe >= 0.12 else 0.4 if roe >= 0.06 else 0.2 if roe > 0 else 0.0)
    if margin is not None:
        comps.append(1.0 if margin >= 0.18 else 0.7 if margin >= 0.10 else 0.4 if margin >= 0.04 else 0.2 if margin > 0 else 0.0)
    if growth is not None:
        comps.append(1.0 if growth >= 0.15 else 0.7 if growth >= 0.05 else 0.5 if growth > 0 else 0.3 if growth >= -0.05 else 0.1)
    if de is not None:
        comps.append(1.0 if de <= 0.3 else 0.7 if de <= 0.7 else 0.5 if de <= 1.2 else 0.3 if de <= 2 else 0.1)
    return _avg(comps)


def _value(pe, pb) -> float | None:
    comps: list[float | None] = []
    if pe is not None and pe > 0:
        comps.append(1.0 if pe <= 15 else 0.8 if pe <= 22 else 0.6 if pe <= 30 else 0.4 if pe <= 40 else 0.2)
    if pb is not None and pb > 0:
        comps.append(1.0 if pb <= 1.5 else 0.8 if pb <= 3 else 0.6 if pb <= 5 else 0.4 if pb <= 8 else 0.2)
    return _avg(comps)


class FundamentalsClient:
    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, Fundamentals]] = {}

    def get(self, symbol: str) -> Fundamentals:
        hit = self._cache.get(symbol)
        if hit and (time.time() - hit[0]) < _TTL:
            return hit[1]
        f = self._fetch(symbol)
        self._cache[symbol] = (time.time(), f)
        return f

    def _fetch(self, symbol: str) -> Fundamentals:
        if classify_asset(symbol) is not AssetClass.EQUITY:
            return Fundamentals(symbol, applicable=False,
                                reasoning="fundamentals apply to equities only")
        raw = _from_openbb(symbol) or _from_yfinance(symbol)
        if not raw:
            return Fundamentals(symbol, applicable=True, source="none",
                                reasoning="no fundamental data available (abstaining)")
        return _score(symbol, raw)


def _score(symbol: str, raw: dict) -> Fundamentals:
    pe, fpe, pb = raw.get("pe"), raw.get("forward_pe"), raw.get("pb")
    roe, margin = raw.get("roe"), raw.get("profit_margin")
    growth, de = raw.get("revenue_growth"), raw.get("debt_to_equity")
    q = _quality(roe, margin, growth, de)
    v = _value(pe, pb)
    quality = q if q is not None else 0.5
    value = v if v is not None else 0.5
    composite = 0.6 * quality + 0.4 * value
    stance = "bullish" if composite >= 0.62 else "bearish" if composite <= 0.40 else "neutral"
    confidence = min(0.7, abs(composite - 0.5) * 1.6)

    bits = []
    if pe is not None:
        bits.append(f"P/E {pe:.1f}")
    if pb is not None:
        bits.append(f"P/B {pb:.1f}")
    if roe is not None:
        bits.append(f"ROE {roe:.0%}")
    if margin is not None:
        bits.append(f"margin {margin:.0%}")
    if growth is not None:
        bits.append(f"rev growth {growth:+.0%}")
    if de is not None:
        bits.append(f"D/E {de:.2f}")
    reasoning = (f"Quality {quality:.0%}, value {value:.0%} -> {stance}. "
                 + ", ".join(bits))
    metrics = {"pe": pe, "forward_pe": fpe, "pb": pb, "roe": roe,
               "profit_margin": margin, "revenue_growth": growth,
               "debt_to_equity": de, "dividend_yield": raw.get("dividend_yield"),
               "market_cap": raw.get("market_cap")}
    return Fundamentals(symbol, applicable=True, source=raw.get("source", "yfinance"),
                        name=raw.get("name", ""), sector=raw.get("sector", ""),
                        metrics=metrics, quality_score=quality, value_score=value,
                        composite=composite, stance=stance, confidence=confidence,
                        reasoning=reasoning)


def _norm_de(de):
    if de is None:
        return None
    return de / 100.0 if de > 5 else de  # yfinance sometimes reports D/E as a percent


def _from_yfinance(symbol: str) -> dict | None:
    try:
        import yfinance as yf
        info = yf.Ticker(symbol).get_info()
        if not info or not isinstance(info, dict):
            return None
        return {
            "source": "yfinance", "name": info.get("longName", ""),
            "sector": info.get("sector", ""),
            "pe": info.get("trailingPE"), "forward_pe": info.get("forwardPE"),
            "pb": info.get("priceToBook"), "roe": info.get("returnOnEquity"),
            "profit_margin": info.get("profitMargins"),
            "revenue_growth": info.get("revenueGrowth"),
            "debt_to_equity": _norm_de(info.get("debtToEquity")),
            "dividend_yield": info.get("dividendYield"), "market_cap": info.get("marketCap"),
        }
    except Exception as exc:  # noqa: BLE001 - any failure -> agent abstains
        logger.info("yfinance fundamentals failed for %s: %s", symbol, exc)
        return None


def _from_openbb(symbol: str) -> dict | None:
    """Use the OpenBB SDK when installed. Best-effort mapping; falls back silently."""
    try:
        from openbb import obb  # type: ignore
    except Exception:  # noqa: BLE001 - not installed -> use yfinance
        return None
    try:
        m = obb.equity.fundamental.metrics(symbol=symbol, provider="yfinance").results[0]
        g = lambda *names: next((getattr(m, n) for n in names if getattr(m, n, None) is not None), None)
        return {
            "source": "openbb", "name": getattr(m, "name", ""),
            "pe": g("pe_ratio", "price_to_earnings"), "forward_pe": g("forward_pe"),
            "pb": g("price_to_book", "pb_ratio"), "roe": g("return_on_equity"),
            "profit_margin": g("net_profit_margin", "profit_margin"),
            "revenue_growth": g("revenue_growth"), "debt_to_equity": _norm_de(g("debt_to_equity")),
            "dividend_yield": g("dividend_yield"), "market_cap": g("market_cap"),
        }
    except Exception as exc:  # noqa: BLE001
        logger.info("OpenBB fundamentals failed for %s: %s", symbol, exc)
        return None


_client: FundamentalsClient | None = None


def get_fundamentals_client() -> FundamentalsClient:
    global _client
    if _client is None:
        _client = FundamentalsClient()
    return _client
