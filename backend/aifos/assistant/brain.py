"""Vision — the AIFOS desk assistant.

LOCAL-FIRST and API-FREE for everything that matters: it routes questions to a
deterministic intent engine that reads/controls live AIFOS state and builds a
world-news brief pinpointing what affects the user's stocks. An external LLM is
used ONLY as a last resort for open-ended questions IF a working key exists —
the core (state Q&A, control, news) never needs one. Honesty rule holds: no
profit guarantees, default stance is HOLD.
"""
from __future__ import annotations

import logging

import httpx

from ..agents.llm import get_llm
from ..config import settings

logger = logging.getLogger("aifos.assistant")

_ALIASES = {
    "reliance": "RELIANCE.NS", "tcs": "TCS.NS", "hdfc": "HDFCBANK.NS",
    "hdfcbank": "HDFCBANK.NS", "infy": "INFY.NS", "infosys": "INFY.NS",
    "nifty": "^NSEI", "nifty50": "^NSEI", "banknifty": "^NSEBANK",
    "bank nifty": "^NSEBANK", "usdinr": "USDINR=X", "eurinr": "EURINR=X",
    "eurusd": "EURUSD=X", "gbpusd": "GBPUSD=X", "bitcoin": "BTC-USD", "btc": "BTC-USD",
    "ethereum": "ETH-USD", "eth": "ETH-USD",
}
# macro keywords whose news affects the whole book
_MACRO = {"rbi", "fed", "federal reserve", "interest rate", " rate ", "inflation", "cpi",
          "gdp", "oil", "crude", "rupee", "dollar", "tariff", "war", "sanction", "recession",
          "budget", "sebi", "fomc", "yuan", "geopolit"}


def engine_name() -> str:
    return "local"  # Vision answers from its own engine; LLM is optional, never required


def _short(s: str) -> str:
    return s.replace(".NS", "").replace("-USD", "").replace("=X", "").replace("^", "")


def _detect_symbol(q: str, universe: list[str]) -> str | None:
    for s in universe:
        if s.lower() in q:
            return s
    for alias, sym in _ALIASES.items():
        if alias in q:
            return sym
    return None


def _affected(title: str, universe: list[str]) -> tuple[list[str], bool]:
    """Which of the user's symbols a headline touches, and whether it's macro."""
    t = f" {title.lower()} "
    hits: set[str] = set()
    for alias, sym in _ALIASES.items():
        if alias in t and sym in universe:
            hits.add(sym)
    for sym in universe:
        root = _short(sym).lower()
        if len(root) >= 3 and f" {root}" in t:
            hits.add(sym)
    macro = any(k in t for k in _MACRO)
    return sorted(hits), macro


# ── optional external LLM (last resort only) ────────────────────────────────
def _groq(prompt: str, system: str) -> str | None:
    if not settings.groq_api_key:
        return None
    try:
        r = httpx.post("https://api.groq.com/openai/v1/chat/completions",
                       headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                       json={"model": settings.groq_model, "temperature": 0.2, "max_tokens": 500,
                             "messages": [{"role": "system", "content": system},
                                          {"role": "user", "content": prompt}]},
                       timeout=settings.llm_timeout_s)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:  # noqa: BLE001
        logger.info("groq failed: %s", exc)
        return None


def _gemini(prompt: str, system: str) -> str | None:
    if not settings.gemini_api_key:
        return None
    try:
        r = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent",
            params={"key": settings.gemini_api_key},
            json={"systemInstruction": {"parts": [{"text": system}]},
                  "contents": [{"parts": [{"text": prompt}]}],
                  "generationConfig": {"temperature": 0.2, "maxOutputTokens": 500}},
            timeout=settings.llm_timeout_s)
        r.raise_for_status()
        cands = r.json().get("candidates", [])
        if cands:
            return "".join(p.get("text", "") for p in cands[0]["content"]["parts"]).strip()
    except Exception as exc:  # noqa: BLE001
        logger.info("gemini failed: %s", exc)
    return None


def _has(q: str, *words: str) -> bool:
    return any(w in q for w in words)


# ── control: Vision can DO things (state changes), fully local ──────────────
def _control(kernel, q: str) -> str | None:
    if _has(q, "kill switch", "halt", "stop trading", "stop all", "emergency", "freeze",
            "panic", "shut it down", "shut down trading"):
        kernel.kill("voice command from Vision")
        return "Done, sir — kill switch tripped. All new trading is halted until you resume."
    if _has(q, "resume", "unfreeze", "restart trading", "arm trading", "turn it back on",
            "re-arm", "rearm", "back on"):
        kernel.resume()
        return "Trading resumed, sir. The desk is armed again (paper unless live is gated on)."
    if _has(q, "autonomous", "auto mode", "take over", "trade on your own", "run yourself"):
        on = not _has(q, "off", "stop", "disable", "pause", "no")
        kernel.set_autonomous(on)
        return f"Autonomous mode {'enabled' if on else 'disabled'}, sir."
    if _has(q, "run a cycle", "run cycle", "scan the market", "scan everything", "scan all",
            "check everything", "sweep the market", "run the universe", "scan the universe"):
        results = kernel.run_universe(execute=True)
        acted = [r for r in results if r.get("executed")]
        holds = sum(1 for r in results if r.get("action") == "HOLD")
        return (f"Swept {len(results)} instruments, sir. {holds} HOLD, {len(acted)} executed. "
                + ("Nothing cleared the bar — holding cash." if not acted
                   else "Acted on: " + ", ".join(_short(r['symbol']) for r in acted)))
    return None


# ── world-news brief: pinpoint what affects YOUR stocks (local) ─────────────
def world_brief(kernel) -> str:
    from ..news.intelligence import market_news, news_intelligence

    uni = settings.universe
    items: list[dict] = []
    try:
        for h in market_news().get("headlines", []):
            aff, macro = _affected(h["title"], uni)
            items.append({**h, "affects": aff, "macro": macro})
    except Exception:  # noqa: BLE001
        pass

    held = [p["symbol"] for p in kernel.portfolio()["positions"]]
    focus = held or [s for s in uni if s.endswith(".NS") or s.startswith("^") or s.endswith("-USD")][:5]
    for sym in focus:
        try:
            for h in news_intelligence(sym).get("headlines", [])[:3]:
                items.append({**h, "affects": [sym], "macro": False})
        except Exception:  # noqa: BLE001
            continue

    def score(it: dict) -> float:
        return (1.2 if it["affects"] else 0) + (0.6 if it["macro"] else 0) + it.get("impact_score", 0)

    items.sort(key=score, reverse=True)
    seen, top = set(), []
    for it in items:
        if it["title"] in seen:
            continue
        seen.add(it["title"])
        top.append(it)
        if len(top) >= 6:
            break
    if not top:
        return "No fresh headlines are reaching me right now, sir — news feeds may be quiet or offline."

    bull = sum(1 for it in top if it["sentiment"] == "bullish")
    bear = sum(1 for it in top if it["sentiment"] == "bearish")
    mood = "risk-on" if bull > bear else "risk-off" if bear > bull else "mixed"
    lines = [f"Here's what's moving and how it touches your book, sir — tone looks {mood}:"]
    for it in top:
        arrow = "▲" if it["sentiment"] == "bullish" else "▼" if it["sentiment"] == "bearish" else "•"
        tag = ", ".join(_short(s) for s in it["affects"]) if it["affects"] else ("macro" if it["macro"] else "broad")
        lines.append(f"{arrow} [{tag}] {it['title']}")
    return "\n".join(lines)


# ── knowledge router (local, reads live state) ──────────────────────────────
def _route(kernel, q: str, sym: str | None) -> str | None:
    pf = kernel.portfolio()
    acct = pf["account"]

    # world / market brief (only when not asking about a specific symbol)
    if not sym and _has(q, "world", "global", "happening", "going on", "around", "headlines",
                        "market news", "what's new", "whats new", "news today", "macro", "everything going"):
        return world_brief(kernel)

    if _has(q, "portfolio", "equity", "balance", "holding", "position", "pnl", "p&l",
            "profit", "loss", "money", "cash", "account", "how much"):
        lines = [f"Equity {acct['equity']:,.0f} {acct['currency']}, cash {acct['cash']:,.0f}, "
                 f"unrealized {pf['unrealized_pnl']:,.0f}, realized {acct['realized_pnl']:,.0f}, "
                 f"{pf['open_positions']} open positions ({pf['mode']} mode)."]
        for p in pf["positions"][:6]:
            lines.append(f"  {_short(p['symbol'])}: {p['qty']} @ {p['avg_price']} (uPnL {p['unrealized_pnl']:,.0f})")
        return "\n".join(lines)

    if _has(q, "risk", "drawdown", "exposure", "safe", "danger", "kill", "limit"):
        risk = kernel.risk_snapshot()
        return (f"Kill switch {'ON' if risk['kill_switch_active'] else 'off'}. Daily P&L "
                f"{risk['daily_pnl']:,.0f} of a {risk['daily_loss_limit']:,.0f} loss limit "
                f"({risk['daily_loss_used_pct']:.0%} used). Confidence floor "
                f"{risk['limits']['confidence_threshold']}, max {risk['limits']['max_open_positions']} "
                f"positions, min R:R {risk['limits']['min_rr_ratio']}.")

    if _has(q, "performance", "analytics", "sharpe", "sortino", "win rate", "winrate", "stats",
            "how am i doing", "returns", "metrics", "profit factor", "expectancy"):
        from ..analytics import portfolio_analytics
        a = portfolio_analytics(kernel.repo)
        if a["closed_trades"] == 0:
            return ("No closed trades yet, sir — performance metrics populate once trades close. "
                    "I won't invent numbers.")
        return (f"{a['closed_trades']} closed trades: win rate {a['win_rate']:.0%}, profit factor "
                f"{a['profit_factor']}, Sharpe {a['sharpe']}, max drawdown {a['max_drawdown']:.1%}, "
                f"expectancy {a['expectancy']:,.0f}.")

    if _has(q, "agent", "committee", "who decided", "vote", "reasoning", "why"):
        ops = None
        if sym:
            d, _ = kernel.analyze(sym, persist=False)
            ops = [o.to_dict() for o in d.opinions]
            head = f"Committee on {_short(sym)} → {d.action} ({d.confidence:.0%}):"
        else:
            rec = kernel.repo.recent_decisions(1)
            if rec:
                ops = rec[0].get("agent_opinions") or []
                head = f"Last decision — {_short(rec[0]['symbol'])} {rec[0]['action']}:"
        if ops:
            voices = [f"  {o['agent']}: {o['stance']} ({o['confidence']:.0%}){' VETO' if o.get('veto') else ''}"
                      for o in ops if o.get("weight", 0) or o.get("veto")][:8]
            return head + "\n" + "\n".join(voices)

    if _has(q, "recent", "activity", "log", "history", "what did you do", "last trade", "trades"):
        recent = kernel.repo.recent_decisions(6)
        if not recent:
            return "Quiet so far, sir — no decisions logged yet. Ask me to scan the market."
        return "Recent decisions:\n" + "\n".join(
            f"  {_short(r['symbol'])} {r['action']} ({r['confidence']:.0%})" for r in recent)

    if sym:
        if _has(q, "news", "headline", "sentiment"):
            from ..news.intelligence import news_intelligence
            ni = news_intelligence(sym)
            if ni.get("count"):
                a = ni["aggregate"]
                heads = "\n".join(f"  [{h['sentiment']}] {h['title']}" for h in ni["headlines"][:5])
                return f"{_short(sym)} news — net {a['sentiment']} ({a['bullish']}↑/{a['bearish']}↓):\n{heads}"
            return f"No live headlines for {_short(sym)} right now, sir."
        if _has(q, "fundamental", "valuation", "pe", "p/e", "value", "quality", "balance sheet"):
            from ..research.fundamentals import get_fundamentals_client
            f = get_fundamentals_client().get(sym)
            return f.reasoning if f.applicable and f.source != "none" else \
                f"No fundamentals for {_short(sym)} (applies to equities)."
        # default: a fresh decision snapshot
        d, _ = kernel.analyze(sym, persist=False)
        return f"{_short(sym)}: I'd {d.action} ({d.side}) at {d.confidence:.0%} confidence. {d.reasoning}"

    if _has(q, "help", "what can you", "command", "abilities", "what do you do"):
        return _help()
    if _has(q, "hello", "hi ", "hey", "yo ", "good morning", "good evening", "who are you", "your name"):
        return (f"I'm {settings.assistant_name}, your AIFOS desk. I see your live portfolio, risk, "
                f"news and the committee's calls — and I can control the desk by voice. "
                f"Try 'what's happening in the world', 'how's my risk', or 'stop trading'.")
    return None


def _help() -> str:
    return (f"I'm {settings.assistant_name}. I run fully on-device — no external AI needed. I can:\n"
            "• tell you what's happening worldwide and which headlines hit YOUR stocks\n"
            "• report portfolio, risk, performance, a symbol's decision/news/fundamentals\n"
            "• CONTROL the desk: 'stop trading' / 'resume' / 'scan the market' / 'autonomous on'\n"
            "I answer only from live data and never promise profit — default is HOLD.")


def answer(kernel, question: str) -> dict:
    q = question.lower().strip()
    sym = _detect_symbol(q, settings.universe)

    ctl = _control(kernel, q)
    if ctl is not None:
        return {"answer": ctl, "engine": "control", "symbol": sym}

    local = _route(kernel, q, sym)
    if local is not None:
        return {"answer": local, "engine": "local", "symbol": sym}

    # open-ended only: use an LLM if (and only if) a working key is configured
    out = _groq(question, _help()) or _gemini(question, _help())
    if not out and get_llm().available():
        out = get_llm().generate(question, _help())
    return {"answer": out or _help(), "engine": "llm" if out else "local", "symbol": sym}
