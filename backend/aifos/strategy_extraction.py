"""Ingest an LLM-extracted strategy (from a video transcript, via the n8n pipeline)
and turn it into a structured, REVIEWABLE record mapped to the closest backtestable
template.

HONEST by design: this extracts and structures *educational* strategy logic for a
human to review, and maps it to an EXISTING, already-tested strategy template so it
can be backtested. It does NOT auto-write novel executable strategies, and it claims
no hidden edge — a human approves before anything influences trading.
"""
from __future__ import annotations


def _blob(payload: dict) -> str:
    parts = [
        str(payload.get("strategy_name", "")), str(payload.get("market", "")),
        str(payload.get("timeframe", "")),
        " ".join(map(str, payload.get("indicators", []) or [])),
        " ".join(map(str, payload.get("entry_conditions", []) or [])),
        " ".join(map(str, payload.get("exit_conditions", []) or [])),
        str(payload.get("strategy_type", "")),
    ]
    return " ".join(parts).lower()


def map_to_template(payload: dict) -> str:
    """Map the extracted concept to the closest EXISTING backtestable strategy."""
    t = _blob(payload)
    if "vwap" in t:
        return "vwap_trend"
    if "bollinger" in t:
        return "bollinger_reversion"
    if "rsi" in t and "macd" in t:
        return "rsi_macd"
    if any(k in t for k in ("breakout", "donchian", "volume spike", "volume expansion", "range breakout")):
        return "breakout_volume"
    if any(k in t for k in ("mean revers", "revert", "fade the")):
        return "mean_reversion"
    if any(k in t for k in ("ema", "moving average", "supertrend", "trend continuation", "ict", "smart money")):
        return "ema_trend"
    return "momentum"


def clarity_score(payload: dict) -> float:
    have = [
        bool(payload.get("indicators")),
        bool(payload.get("entry_conditions")),
        bool(payload.get("exit_conditions")),
        bool(payload.get("risk_management") or payload.get("stop_loss") or payload.get("take_profit")),
    ]
    return round(sum(have) / len(have), 2)


def analyze_extraction(payload: dict) -> dict:
    """Validate + score + map an extracted strategy (no execution, no edge claims)."""
    clarity = clarity_score(payload)
    issues: list[str] = []
    if not payload.get("indicators"):
        issues.append("no indicators specified")
    if not payload.get("entry_conditions"):
        issues.append("no entry conditions")
    if not payload.get("exit_conditions"):
        issues.append("no exit / stop conditions")
    return {
        "strategy_name": payload.get("strategy_name") or "Unnamed strategy",
        "source": payload.get("source", ""),
        "market": payload.get("market"),
        "timeframe": payload.get("timeframe"),
        "indicators": payload.get("indicators", []) or [],
        "mapped_template": map_to_template(payload),
        "clarity": clarity,
        "needs_review": clarity < 0.75 or bool(issues),
        "issues": issues,
        "note": "Extracted educational logic, mapped to an existing tested template for backtesting. "
                "NOT auto-deployed and claims no edge — a human reviews & approves before it can trade.",
    }
