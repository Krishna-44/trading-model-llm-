"""Candlestick pattern detection — deterministic geometry on OHLCV bars.

No computer vision, no screenshots: classic patterns read directly from the
candle math, each carrying a plain-English 'why' so it doubles as a learning
aid. Patterns are probabilistic context, never guarantees.
"""
from __future__ import annotations

import pandas as pd


def _candle(df: pd.DataFrame, i: int) -> dict:
    r = df.iloc[i]
    o, h, low, c = float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"])
    body = abs(c - o)
    rng = (h - low) or 1e-9
    return {"o": o, "h": h, "l": low, "c": c, "body": body, "rng": rng,
            "upper": h - max(o, c), "lower": min(o, c) - low, "green": c >= o}


def detect_patterns(df: pd.DataFrame) -> list[dict]:
    """Patterns present on the latest bar(s). Each: name, bias, strength, meaning."""
    if len(df) < 3:
        return []
    a = _candle(df, -1)   # latest
    b = _candle(df, -2)   # previous
    c2 = _candle(df, -3)  # two back
    closes = df["close"]
    n = len(df)
    up_trend = n >= 6 and float(closes.iloc[-1]) > float(closes.iloc[-6])
    down_trend = n >= 6 and float(closes.iloc[-1]) < float(closes.iloc[-6])
    bp = a["body"] / a["rng"]  # body as fraction of range

    out: list[dict] = []

    def add(name, bias, meaning, strength=0.5):
        out.append({"name": name, "bias": bias, "strength": round(float(strength), 2), "meaning": meaning})

    # --- single-candle ---
    if bp < 0.1:
        add("Doji", "neutral",
            "Open ≈ close — indecision, buyers and sellers balanced. Wait for the next candle to pick a side.", 0.4)
    elif bp > 0.9:
        add("Marubozu", "bullish" if a["green"] else "bearish",
            "Almost all body, no wicks — one side dominated the entire session. Strong momentum in that direction.", 0.6)

    if a["lower"] > 2 * a["body"] and a["upper"] < a["body"] and bp < 0.5:
        add("Hammer", "bullish",
            "Long lower wick, small body on top — sellers pushed price down but buyers slammed it back up. "
            "Bullish, especially after a decline.", 0.55 if down_trend else 0.4)
    if a["upper"] > 2 * a["body"] and a["lower"] < a["body"] and bp < 0.5:
        add("Shooting star", "bearish",
            "Long upper wick — buyers pushed up but were rejected hard. Bearish, especially after a rally.",
            0.55 if up_trend else 0.4)
    if 0.1 <= bp <= 0.3 and a["upper"] > a["body"] and a["lower"] > a["body"]:
        add("Spinning top", "neutral",
            "Small body with wicks both sides — a tug-of-war with no winner. Indecision.", 0.35)

    # --- two-candle ---
    if a["green"] and not b["green"] and a["c"] >= b["o"] and a["o"] <= b["c"]:
        add("Bullish engulfing", "bullish",
            "Today's green body fully engulfs yesterday's red — buyers overwhelmed sellers. "
            "A common reversal-up signal; confirm with the next bar.", 0.65)
    if not a["green"] and b["green"] and a["c"] <= b["o"] and a["o"] >= b["c"]:
        add("Bearish engulfing", "bearish",
            "Today's red body fully engulfs yesterday's green — sellers took control. "
            "A common reversal-down signal; confirm with the next bar.", 0.65)
    if a["h"] <= b["h"] and a["l"] >= b["l"]:
        add("Inside bar", "neutral",
            "Today's whole range sits inside yesterday's — consolidation. A breakout (either way) often follows.", 0.4)

    # --- three-candle ---
    if c2["c"] < c2["o"] and b["body"] < c2["body"] * 0.5 and a["green"] and a["c"] > (c2["o"] + c2["c"]) / 2:
        add("Morning star", "bullish",
            "Big red, then a small indecision candle, then a strong green closing back into the first — "
            "a classic bottoming reversal.", 0.7)
    if c2["c"] > c2["o"] and b["body"] < c2["body"] * 0.5 and not a["green"] and a["c"] < (c2["o"] + c2["c"]) / 2:
        add("Evening star", "bearish",
            "Big green, then a small candle, then a strong red — a classic topping reversal.", 0.7)

    return out


def candle_read(df: pd.DataFrame) -> dict:
    """Aggregate the latest candlestick patterns into a bias + a learning summary."""
    pats = detect_patterns(df)
    score = 0.0
    for p in pats:
        if p["bias"] == "bullish":
            score += p["strength"]
        elif p["bias"] == "bearish":
            score -= p["strength"]
    score = max(-1.0, min(1.0, score))
    bias = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"
    return {
        "patterns": pats,
        "bias": bias,
        "score": round(score, 2),
        "count": len(pats),
        "summary": (", ".join(p["name"] for p in pats) if pats
                    else "No notable candlestick pattern on the latest bar."),
        "note": "Candlestick patterns are probabilistic context from price geometry — not guarantees. "
                "Confirm with trend, volume and risk before acting.",
    }
