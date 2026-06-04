"""AI video-learning seed — the multimodal Trader Knowledge pipeline, stage 1.

Paste a YouTube URL -> fetch the transcript -> extract a structured, backtestable
strategy. Uses the LLM if available; otherwise a deterministic keyword extractor
so it still produces real structure offline. Chart-frame CV / OCR are the next
stages (not built) — this is the honest, working seed."""
from __future__ import annotations

import json
import logging
import re

from ..agents.llm import get_llm

logger = logging.getLogger("aifos.learn")

_INDICATORS = ["rsi", "macd", "ema", "sma", "moving average", "bollinger", "vwap",
               "atr", "stochastic", "fibonacci", "support", "resistance", "order block",
               "liquidity", "fair value gap", "supply", "demand", "trendline", "volume"]
_RISK = ["stop loss", "stop-loss", "take profit", "risk reward", "risk-reward",
         "risk management", "position size", "r:r", "drawdown"]
_ENTRY = ["entry", "buy when", "go long", "enter long", "breakout", "pullback", "retest"]
_EXIT = ["exit", "sell when", "go short", "take profit", "close position", "trail"]


def _video_id(url: str) -> str | None:
    m = re.search(r"(?:v=|youtu\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{11})", url)
    if m:
        return m.group(1)
    return url if re.fullmatch(r"[A-Za-z0-9_-]{11}", url) else None


def fetch_transcript(url: str) -> str:
    vid = _video_id(url)
    if not vid:
        raise ValueError("could not parse a YouTube video id from the input")
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as e:
        raise RuntimeError("pip install -r requirements-learn.txt (youtube-transcript-api)") from e
    # support both the old classmethod API (<=0.6) and the new instance API (>=1.0)
    if hasattr(YouTubeTranscriptApi, "get_transcript"):
        chunks = YouTubeTranscriptApi.get_transcript(vid)
    else:
        fetched = YouTubeTranscriptApi().fetch(vid)
        chunks = (fetched.to_raw_data() if hasattr(fetched, "to_raw_data")
                  else [{"text": getattr(s, "text", str(s))} for s in fetched])
    return " ".join(c.get("text", "") for c in chunks)


def _heuristic_extract(transcript: str) -> dict:
    t = transcript.lower()
    found = lambda kws: sorted({k for k in kws if k in t})
    return {
        "indicators": found(_INDICATORS), "entry_rules": found(_ENTRY),
        "exit_rules": found(_EXIT), "risk_management": found(_RISK),
        "uses_stop_loss": any(k in t for k in ("stop loss", "stop-loss")),
        "summary": "Heuristic keyword extraction (no LLM connected).",
        "method": "heuristic",
    }


_SYS = ("You extract a structured, BACKTESTABLE trading strategy from a transcript. "
        "Return ONLY JSON with keys: indicators (array), entry_rules (array), "
        "exit_rules (array), risk_management (array), market_conditions (array), "
        "summary (string). Be faithful to the transcript; never invent rules.")


def extract_strategy(transcript: str) -> dict:
    out = get_llm().generate(
        f"Transcript excerpt:\n{transcript[:6000]}\n\nExtract the strategy as JSON.", system=_SYS)
    if out:
        try:
            data = json.loads(out[out.find("{"):out.rfind("}") + 1])
            data["method"] = "llm"
            return data
        except Exception:  # noqa: BLE001 - fall back to heuristic on bad JSON
            pass
    return _heuristic_extract(transcript)


def learn_from_video(url: str) -> dict:
    transcript = fetch_transcript(url)
    return {
        "video_id": _video_id(url), "length_chars": len(transcript),
        "excerpt": transcript[:400], "strategy": extract_strategy(transcript),
        "next_steps": "Chart-frame CV + indicator detection are the next pipeline stages.",
    }
