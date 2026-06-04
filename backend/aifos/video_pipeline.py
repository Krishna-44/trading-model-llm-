"""Turn a YouTube link into a structured strategy payload — inside AIFOS.

This is the extraction the n8n workflow would do, hosted natively so the
Video → Strategy queue works with no external service:
  fetch transcript (youtube-transcript-api, no key)
   → extract structured JSON (Gemini if a key exists, else keyword heuristic)
   → hand to kernel.ingest_extracted (map to a tested template + backtest).

Honesty rule holds: it extracts only what the video states; it never invents
edge or profitability. If there's no transcript, it returns an honest error.
"""
from __future__ import annotations

import json
import logging
import re

import httpx

from .config import settings

logger = logging.getLogger("aifos.video")

_YT_ID = re.compile(r"(?:v=|/shorts/|youtu\.be/|/embed/|/v/|/live/)([A-Za-z0-9_-]{11})")
_EN = ["en", "en-IN", "en-US", "en-GB"]


def extract_video_id(url: str) -> str | None:
    m = _YT_ID.search(url or "")
    if m:
        return m.group(1)
    s = (url or "").strip()
    return s if re.fullmatch(r"[A-Za-z0-9_-]{11}", s) else None


def fetch_title(url: str) -> str:
    """Real video title via YouTube oEmbed (no API key)."""
    try:
        r = httpx.get("https://www.youtube.com/oembed",
                      params={"url": url, "format": "json"}, timeout=10)
        if r.status_code == 200:
            return str(r.json().get("title", "")).strip()
    except Exception:  # noqa: BLE001
        pass
    return ""


def fetch_transcript(url: str) -> tuple[str, str | None]:
    """Return (transcript_text, error). Prefers an English transcript; otherwise
    translates an available one to English; otherwise takes whatever exists."""
    vid = extract_video_id(url)
    if not vid:
        return "", "could not parse a YouTube video id from that URL"
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        api = YouTubeTranscriptApi()
        tl = api.list(vid)
        t = None
        for finder in ("find_manually_created_transcript", "find_generated_transcript", "find_transcript"):
            try:
                t = getattr(tl, finder)(_EN)
                break
            except Exception:  # noqa: BLE001
                t = None
        if t is None:  # no English — take any, translate to en if possible
            for x in tl:
                t = x
                break
            if t is not None and getattr(t, "is_translatable", False) and t.language_code != "en":
                try:
                    t = t.translate("en")
                except Exception:  # noqa: BLE001
                    pass
        if t is None:
            return "", "no transcript/captions available for this video"
        text = " ".join(s.text for s in t.fetch()).strip()
        if not text:
            return "", "transcript was empty"
        return text, None
    except Exception as exc:  # noqa: BLE001
        name = type(exc).__name__
        if "Disabled" in name:
            return "", "captions are disabled on this video"
        if "Unavailable" in name:
            return "", "video is unavailable/private"
        if "NoTranscript" in name:
            return "", "no transcript found for this video"
        return "", f"transcript fetch failed ({name})"


# ── on-device keyword extractor (API-free, always works) ────────────────────
_KW = {
    "vwap": "vwap", "ema": "ema", "exponential moving average": "ema", "sma": "sma",
    "moving average": "moving average", "rsi": "rsi", "macd": "macd",
    "bollinger": "bollinger", "supertrend": "supertrend", "super trend": "supertrend",
    "breakout": "breakout", "donchian": "donchian", "volume": "volume",
    "order block": "ict", " ict": "ict", "smart money": "smc", " smc": "smc",
    "fibonacci": "fibonacci", "pivot": "pivot", "atr": "atr", "adx": "adx",
    "stochastic": "stochastic", "momentum": "momentum", "candlestick": "candlestick",
    "price action": "price action", "mean revert": "mean-reversion",
    "opening range": "opening-range", " orb": "opening-range", "gap up": "gap",
    "gap down": "gap", "relative strength": "relative-strength", "heikin": "heikin-ashi",
    "ichimoku": "ichimoku", "camarilla": "camarilla", "moving average convergence": "macd",
}
_ENTRY_KW = ("buy", "enter", "entry", "go long", "long position", "breakout above",
             "cross above", "crosses above", "above vwap", "above the high", "when price",
             "signal to buy", "we go long", "take the trade")
_EXIT_KW = ("sell", "exit", "target", "stop loss", "stoploss", "stop-loss", "book profit",
            "square off", "squareoff", "take profit", "trail", "trailing", "below vwap",
            "our target", "book the profit")
_TF = re.compile(r"(\d+)\s*-?\s*(min|minute|hour|hr|day|daily|week|weekly)", re.I)
_RR = re.compile(r"1\s*[:\-]?\s*(?:is\s*to\s*)?([2-9])(?:\s*r|\s*risk|\s*reward|\b)", re.I)


def _phrases(transcript: str, kws: tuple[str, ...], limit: int = 3) -> list[str]:
    # captions rarely have reliable sentence punctuation, so window into short
    # ~22-word slices — each candidate phrase is then short and self-contained
    words = transcript.split()
    chunks = [" ".join(words[i:i + 22]) for i in range(0, len(words), 22)]
    out: list[str] = []
    seen: set[str] = set()
    for c in chunks:
        cl = c.lower()
        # a real signal line references a level/number — this filters out intro fluff
        if any(k in cl for k in kws) and re.search(r"\d", c):
            phrase = re.sub(r"\s+", " ", c).strip()[:160]
            key = phrase.lower()[:50]
            if phrase and key not in seen:
                seen.add(key)
                out.append(phrase)
        if len(out) >= limit:
            break
    return out


def _heuristic_extract(transcript: str, title: str) -> dict:
    low = f" {transcript.lower()} "
    inds = sorted({v for k, v in _KW.items() if k in low})
    stype = ("intraday" if ("intraday" in low or "day trad" in low) else "scalping" if "scalp" in low
             else "swing" if "swing" in low else "options" if "option" in low else "")
    tf = ""
    m = _TF.search(transcript)
    if m:
        tf = f"{m.group(1)} {m.group(2).lower()}"
    risk: dict = {}
    rr = _RR.search(transcript)
    if rr:
        risk["rr_ratio"] = f"1:{rr.group(1)}"
    if any(s in low for s in ("stop loss", "stoploss", "stop-loss")):
        risk["stop"] = "stop-loss mentioned"
    return {"strategy_name": title or "Extracted strategy", "market": "", "timeframe": tf,
            "indicators": inds, "entry_conditions": _phrases(transcript, _ENTRY_KW),
            "exit_conditions": _phrases(transcript, _EXIT_KW),
            "risk_management": risk, "strategy_type": stype}


def _agentllm_extract(transcript: str, title: str) -> dict | None:
    """Try AIFOS's configured LLM (Ollama/Anthropic/OpenAI) — free + no billing if
    Ollama is running locally. Returns None if no provider is reachable."""
    from .agents.llm import get_llm
    llm = get_llm()
    if not llm.available():
        return None
    out = llm.generate(
        f"Video title: {title}\n\nTranscript:\n{transcript[:8000]}\n\nReturn ONLY the JSON object.",
        _SYS)
    if not out:
        return None
    try:
        m = re.search(r"\{.*\}", out, re.S)
        data = json.loads(m.group(0) if m else out)
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        return None


# ── Gemini structured extraction (uses the configured key) ──────────────────
_SYS = (
    "You extract trading-strategy logic from a video transcript into STRICT JSON. "
    "Extract ONLY what is explicitly stated or strongly implied — do NOT invent rules, "
    "hidden edge, timeframes, or profitability claims. Keys: strategy_name, market, "
    "timeframe, indicators (array of short tokens like 'vwap','rsi','ema','breakout'), "
    "entry_conditions (array), exit_conditions (array), risk_management (object with "
    "risk_per_trade and rr_ratio), strategy_type (one of scalping, intraday, swing, "
    "options, trend-following, mean-reversion, smc, ict, volatility). Leave a field "
    "empty if the video does not state it."
)


def _gemini_extract(transcript: str, title: str) -> dict | None:
    if not settings.gemini_api_key:
        return None
    prompt = f"Video title: {title}\n\nTranscript:\n{transcript[:12000]}"
    try:
        r = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent",
            params={"key": settings.gemini_api_key},
            json={"systemInstruction": {"parts": [{"text": _SYS}]},
                  "contents": [{"parts": [{"text": prompt}]}],
                  "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2048,
                                       "responseMimeType": "application/json"}},
            timeout=max(settings.llm_timeout_s, 30))
        r.raise_for_status()
        cands = r.json().get("candidates", [])
        if not cands:
            return None
        txt = "".join(p.get("text", "") for p in cands[0].get("content", {}).get("parts", [])).strip()
        data = json.loads(txt)
        return data if isinstance(data, dict) and data.get("indicators") is not None else (data if isinstance(data, dict) else None)
    except Exception as exc:  # noqa: BLE001
        logger.info("gemini extract failed: %s", exc)
        return None


def _ok(p) -> bool:
    return isinstance(p, dict) and bool(p.get("indicators") or p.get("entry_conditions"))


def extract_strategy(transcript: str, title: str = "", url: str = "") -> tuple[dict, str]:
    """Return (payload, source). Tries Gemini → AIFOS LLM (Ollama/etc.) → on-device
    keyword extractor, so it always produces an honest result."""
    payload, source = _gemini_extract(transcript, title), "gemini"
    if not _ok(payload):
        payload, source = _agentllm_extract(transcript, title), "llm"
    if not _ok(payload):
        payload, source = _heuristic_extract(transcript, title), "keywords"
    low = transcript.lower()
    if not payload.get("market"):
        payload["market"] = ("BANKNIFTY" if ("bank nifty" in low or "banknifty" in low)
                             else "NIFTY" if "nifty" in low else "")
    if title and not payload.get("strategy_name"):
        payload["strategy_name"] = title
    payload["source"] = url or title
    return payload, source
