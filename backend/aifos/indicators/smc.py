"""Smart Money Concepts (SMC / ICT) — deterministic price-structure detectors.

No ML and no paid feeds: pure geometry on OHLC bars. Each detector returns plain
numbers so the Smart Money agent and the explainability tree can cite exactly
what fired and why. These describe *where* institutional liquidity tends to sit;
they are probabilistic context, never guarantees.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def swing_points(df: pd.DataFrame, left: int = 2, right: int = 2):
    """Fractal swing highs/lows (a local extreme with `left`/`right` neighbours)."""
    high, low = df["high"], df["low"]
    n = len(df)
    sh = [False] * n
    sl = [False] * n
    for i in range(left, n - right):
        win_h = high.iloc[i - left:i + right + 1]
        win_l = low.iloc[i - left:i + right + 1]
        if high.iloc[i] >= win_h.max():
            sh[i] = True
        if low.iloc[i] <= win_l.min():
            sl[i] = True
    return sh, sl


def market_structure(df: pd.DataFrame, left: int = 2, right: int = 2) -> dict:
    """BOS (break of structure → continuation) vs CHOCH (change of character →
    possible reversal), inferred from the sequence of swing highs/lows."""
    sh, sl = swing_points(df, left, right)
    highs = [df["high"].iloc[i] for i in range(len(df)) if sh[i]]
    lows = [df["low"].iloc[i] for i in range(len(df)) if sl[i]]
    close = float(df["close"].iloc[-1])
    last_sh = float(highs[-1]) if highs else None
    last_sl = float(lows[-1]) if lows else None

    bias = "neutral"
    if len(highs) >= 2 and len(lows) >= 2:
        hh, hl = highs[-1] > highs[-2], lows[-1] > lows[-2]
        lh, ll = highs[-1] < highs[-2], lows[-1] < lows[-2]
        if hh and hl:
            bias = "bullish"
        elif lh and ll:
            bias = "bearish"

    event = "none"
    if last_sh is not None and close > last_sh:
        event = "BOS_up" if bias == "bullish" else "CHOCH_up"
    elif last_sl is not None and close < last_sl:
        event = "BOS_down" if bias == "bearish" else "CHOCH_down"

    return {"bias": bias, "event": event,
            "last_swing_high": round(last_sh, 4) if last_sh is not None else None,
            "last_swing_low": round(last_sl, 4) if last_sl is not None else None,
            "swing_highs": len(highs), "swing_lows": len(lows)}


def fair_value_gaps(df: pd.DataFrame, lookback: int = 60) -> dict:
    """3-candle imbalance (FVG). Bullish: low[i] > high[i-2]; bearish: high[i] < low[i-2].
    Returns the nearest unfilled gap to current price."""
    high, low, close = df["high"], df["low"], df["close"]
    px = float(close.iloc[-1])
    gaps = []
    start = max(2, len(df) - lookback)
    for i in range(start, len(df)):
        if low.iloc[i] > high.iloc[i - 2]:
            gaps.append({"type": "bullish", "low": float(high.iloc[i - 2]), "high": float(low.iloc[i])})
        elif high.iloc[i] < low.iloc[i - 2]:
            gaps.append({"type": "bearish", "low": float(high.iloc[i]), "high": float(low.iloc[i - 2])})
    unfilled = [g for g in gaps if not (g["low"] <= px <= g["high"])]
    nearest = min(unfilled, key=lambda g: abs((g["low"] + g["high"]) / 2 - px), default=None)
    if nearest:
        nearest = {"type": nearest["type"], "low": round(nearest["low"], 4),
                   "high": round(nearest["high"], 4),
                   "mid": round((nearest["low"] + nearest["high"]) / 2, 4)}
    return {"count": len(gaps), "nearest_unfilled": nearest}


def order_blocks(df: pd.DataFrame, lookback: int = 60, impulse: float = 1.5) -> dict:
    """Last opposing candle before an impulsive move — where institutions likely
    filled. Bullish OB = last down candle before a strong up-move (acts as support)."""
    o, c, high, low = df["open"], df["close"], df["high"], df["low"]
    body = c - o
    avg_body = body.abs().rolling(20, min_periods=5).mean()
    px = float(c.iloc[-1])
    bull_ob = bear_ob = None
    start = max(6, len(df) - lookback)
    for i in range(start, len(df)):
        ab = avg_body.iloc[i]
        if pd.isna(ab) or ab == 0:
            continue
        if body.iloc[i] > impulse * ab:
            for j in range(i - 1, max(0, i - 6), -1):
                if c.iloc[j] < o.iloc[j]:
                    bull_ob = {"low": float(low.iloc[j]), "high": float(high.iloc[j])}
                    break
        elif -body.iloc[i] > impulse * ab:
            for j in range(i - 1, max(0, i - 6), -1):
                if c.iloc[j] > o.iloc[j]:
                    bear_ob = {"low": float(low.iloc[j]), "high": float(high.iloc[j])}
                    break

    def _fmt(ob):
        if not ob:
            return None
        return {"low": round(ob["low"], 4), "high": round(ob["high"], 4),
                "mid": round((ob["low"] + ob["high"]) / 2, 4)}

    return {"bullish_ob": _fmt(bull_ob), "bearish_ob": _fmt(bear_ob), "price": round(px, 4)}


def premium_discount(df: pd.DataFrame, lookback: int = 50) -> dict:
    """Where price sits in the recent dealing range: discount (<0.45) favours longs,
    premium (>0.55) favours shorts (institutional 'buy low / sell high')."""
    hh = float(df["high"].iloc[-lookback:].max())
    ll = float(df["low"].iloc[-lookback:].min())
    px = float(df["close"].iloc[-1])
    pos = (px - ll) / (hh - ll) if hh > ll else 0.5
    zone = "discount" if pos < 0.45 else "premium" if pos > 0.55 else "equilibrium"
    return {"position": round(pos, 3), "zone": zone,
            "range_high": round(hh, 4), "range_low": round(ll, 4)}


def liquidity_sweep(df: pd.DataFrame, lookback: int = 20) -> dict:
    """A wick beyond a prior swing extreme that closes back inside — a stop-hunt /
    liquidity grab that often precedes a reversal."""
    high, low, close = df["high"], df["low"], df["close"]
    if len(df) < lookback + 2:
        return {"swept": "none"}
    prior_high = float(high.iloc[-lookback - 1:-1].max())
    prior_low = float(low.iloc[-lookback - 1:-1].min())
    last_high, last_low, last_close = float(high.iloc[-1]), float(low.iloc[-1]), float(close.iloc[-1])
    if last_high > prior_high and last_close < prior_high:
        return {"swept": "sell_side_grab_high", "level": round(prior_high, 4)}  # bearish
    if last_low < prior_low and last_close > prior_low:
        return {"swept": "buy_side_grab_low", "level": round(prior_low, 4)}      # bullish
    return {"swept": "none"}


def smc_signals(df: pd.DataFrame) -> dict:
    """Aggregate the SMC reads into a single directional bias + score in [-1, 1]."""
    if len(df) < 30:
        return {"bias": "neutral", "score": 0.0, "components": {},
                "reasoning": "insufficient history for SMC"}
    struct = market_structure(df)
    fvg = fair_value_gaps(df)
    ob = order_blocks(df)
    zone = premium_discount(df)
    sweep = liquidity_sweep(df)

    score = 0.0
    notes: list[str] = []
    if struct["event"].endswith("up"):
        score += 0.35; notes.append(f"{struct['event']} over {struct['last_swing_high']}")
    elif struct["event"].endswith("down"):
        score -= 0.35; notes.append(f"{struct['event']} under {struct['last_swing_low']}")
    elif struct["bias"] == "bullish":
        score += 0.15; notes.append("HH/HL structure")
    elif struct["bias"] == "bearish":
        score -= 0.15; notes.append("LH/LL structure")

    if zone["zone"] == "discount":
        score += 0.20; notes.append("discount zone (favours longs)")
    elif zone["zone"] == "premium":
        score -= 0.20; notes.append("premium zone (favours shorts)")

    if sweep["swept"] == "buy_side_grab_low":
        score += 0.20; notes.append(f"liquidity grab below {sweep['level']}")
    elif sweep["swept"] == "sell_side_grab_high":
        score -= 0.20; notes.append(f"liquidity grab above {sweep['level']}")

    if fvg["nearest_unfilled"]:
        if fvg["nearest_unfilled"]["type"] == "bullish":
            score += 0.10; notes.append("unfilled bullish FVG")
        else:
            score -= 0.10; notes.append("unfilled bearish FVG")

    score = float(max(-1.0, min(1.0, score)))
    bias = "bullish" if score > 0.12 else "bearish" if score < -0.12 else "neutral"
    return {"bias": bias, "score": round(score, 3),
            "components": {"structure": struct, "fvg": fvg, "order_block": ob,
                           "zone": zone, "sweep": sweep},
            "reasoning": "; ".join(notes) or "no clear SMC edge"}
