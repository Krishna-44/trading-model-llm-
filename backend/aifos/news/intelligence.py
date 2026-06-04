"""AI News Intelligence — real headlines + sentiment/impact scoring.

Working slice of the spec: pulls REAL headlines from Yahoo Finance (via yfinance,
keyless), scores each for sentiment + market-impact + confidence with a financial
lexicon (LLM-upgradable), and aggregates a per-symbol read that the News agent
votes with. Multi-source aggregation (Reuters/Twitter/Reddit/Telegram), causal
graphs, manipulation detection and historical-similarity are staged, not faked.
"""
from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET

import httpx

from ..config import settings
from .memory import get_news_memory

logger = logging.getLogger("aifos.news")
_TTL = 600  # 10 min
_cache: dict[str, tuple[float, dict]] = {}

_BULL = {"beat", "beats", "surge", "surges", "surged", "jump", "jumps", "rally", "rallies",
         "record", "upgrade", "upgraded", "soar", "soars", "gain", "gains", "profit",
         "profits", "win", "wins", "approval", "approved", "bullish", "outperform", "raise",
         "raised", "strong", "growth", "expansion", "acquire", "acquires", "buyback", "dividend"}
_BEAR = {"miss", "misses", "missed", "plunge", "plunges", "slump", "fall", "falls", "drop",
         "drops", "cut", "cuts", "downgrade", "downgraded", "probe", "lawsuit", "fraud", "fine",
         "fined", "layoff", "layoffs", "loss", "losses", "warning", "warns", "bearish",
         "underperform", "weak", "decline", "declines", "default", "bankruptcy", "crash",
         "selloff", "recall", "resign", "resigns", "resignation", "halt", "ban"}
_HIGH_IMPACT = {"fed", "rbi", "rate", "inflation", "cpi", "earnings", "merger", "acquisition",
                "lawsuit", "fraud", "crash", "war", "sanction", "downgrade", "upgrade",
                "guidance", "bankruptcy", "recession", "stimulus", "default"}


def _analyze(title: str) -> dict:
    words = set(re.findall(r"[a-z]+", title.lower()))
    bull, bear = len(words & _BULL), len(words & _BEAR)
    hi = len(words & _HIGH_IMPACT)
    net = bull - bear
    sentiment = "bullish" if net > 0 else "bearish" if net < 0 else "neutral"
    impact = min(1.0, 0.2 + 0.18 * (bull + bear) + 0.3 * hi)
    confidence = min(0.8, 0.3 + 0.15 * abs(net) + 0.1 * hi)
    return {"sentiment": sentiment, "impact_score": round(impact, 2),
            "confidence": round(confidence, 2)}


def _newsapi(query: str, limit: int = 8) -> list[dict]:
    try:
        r = httpx.get("https://newsapi.org/v2/everything",
                      params={"q": query, "pageSize": limit, "sortBy": "publishedAt",
                              "language": "en", "apiKey": settings.news_api_key}, timeout=8)
        r.raise_for_status()
        return [{"title": a.get("title", ""),
                 "publisher": (a.get("source") or {}).get("name", "NewsAPI"),
                 "link": a.get("url", ""), "ts": 0, "pubDate": a.get("publishedAt", "")}
                for a in r.json().get("articles", []) if a.get("title")]
    except Exception as exc:  # noqa: BLE001
        logger.info("newsapi failed: %s", exc)
        return []


def fetch_rss(feeds: list[str], limit: int = 14) -> list[dict]:
    items: list[dict] = []
    for url in feeds:
        try:
            r = httpx.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0 AIFOS"})
            r.raise_for_status()
            root = ET.fromstring(r.content)
            src = url.split("/")[2] if "//" in url else url
            for it in root.iter("item"):
                title = (it.findtext("title") or "").strip()
                if title:
                    items.append({"title": title, "publisher": src,
                                  "link": (it.findtext("link") or "").strip(), "ts": 0,
                                  "pubDate": (it.findtext("pubDate") or "").strip()})
        except Exception as exc:  # noqa: BLE001
            logger.info("rss %s failed: %s", url, exc)
    return items[:limit]


def market_news(limit: int = 14) -> dict:
    """Broad market news via RSS (Economic Times / Moneycontrol / CNBC ...)."""
    hit = _cache.get("__market__")
    if hit and (time.time() - hit[0]) < _TTL:
        return hit[1]
    analyzed = [{**h, **_analyze(h["title"])} for h in fetch_rss(settings.rss_feeds, limit)]
    mem = get_news_memory()
    for a in analyzed:
        mem.record(a.get("publisher", "market"), a["title"], 0, a["sentiment"], a["impact_score"])
    bull = sum(1 for a in analyzed if a["sentiment"] == "bullish")
    bear = sum(1 for a in analyzed if a["sentiment"] == "bearish")
    result = {"count": len(analyzed), "headlines": analyzed,
              "aggregate": {"bullish": bull, "bearish": bear,
                            "sentiment": "bullish" if bull > bear else "bearish" if bear > bull else "neutral"}}
    _cache["__market__"] = (time.time(), result)
    return result


def fetch_headlines(symbol: str, limit: int = 10) -> list[dict]:
    try:
        import yfinance as yf
        raw = yf.Ticker(symbol).news or []
    except Exception as exc:  # noqa: BLE001
        logger.info("news fetch failed for %s: %s", symbol, exc)
        return []
    out: list[dict] = []
    for item in raw[:limit]:
        c = item.get("content", item)  # robust to flat (old) + nested (new) schema
        title = c.get("title") or item.get("title")
        if not title:
            continue
        pub = ((c.get("provider") or {}).get("displayName")
               or item.get("publisher") or "")
        link = ((c.get("canonicalUrl") or {}).get("url") or item.get("link") or "")
        out.append({"title": title, "publisher": pub, "link": link,
                    "ts": item.get("providerPublishTime") or 0,
                    "pubDate": c.get("pubDate", "")})
    if settings.news_api_key:  # broaden beyond Yahoo when a NewsAPI key is set
        out.extend(_newsapi(symbol.replace(".NS", "").replace("-USD", ""), limit=limit))
    return out[:limit]


def news_intelligence(symbol: str, limit: int = 10) -> dict:
    hit = _cache.get(symbol)
    if hit and (time.time() - hit[0]) < _TTL:
        return hit[1]
    heads = fetch_headlines(symbol, limit)
    analyzed = [{**h, **_analyze(h["title"])} for h in heads]
    n = len(analyzed) or 1
    bull = sum(1 for a in analyzed if a["sentiment"] == "bullish")
    bear = sum(1 for a in analyzed if a["sentiment"] == "bearish")
    net = (bull - bear) / n
    agg = {
        "sentiment": "bullish" if net > 0.1 else "bearish" if net < -0.1 else "neutral",
        "net": round(net, 2), "bullish": bull, "bearish": bear,
        "avg_impact": round(sum(a["impact_score"] for a in analyzed) / n, 2) if analyzed else 0.0,
    }
    mem = get_news_memory()
    for a in analyzed:
        mem.record(symbol, a["title"], int(a.get("ts") or 0), a["sentiment"], a["impact_score"])
    result = {"symbol": symbol, "count": len(analyzed), "headlines": analyzed,
              "aggregate": agg, "memory": mem.stats()}
    _cache[symbol] = (time.time(), result)
    return result


def news_ticker(symbols: list[str], per: int = 2) -> list[dict]:
    """Flatten top headlines across a few symbols for the scrolling ticker."""
    items: list[dict] = []
    for s in symbols:
        try:
            for a in news_intelligence(s)["headlines"][:per]:
                items.append({"symbol": s, "title": a["title"], "sentiment": a["sentiment"],
                              "impact_score": a["impact_score"]})
        except Exception:  # noqa: BLE001
            continue
    return items
