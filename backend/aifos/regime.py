"""Market regime detection — classify the environment so strategies can adapt.

trending_up / trending_down / ranging / volatile / panic, derived from ADX (trend
strength), the realized-vol ratio (stress) and EMA slope (direction). Deterministic
and fully explainable; feeds adaptive agent weighting in the committee.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .indicators import adx as adx_ind
from .indicators import ema, realized_vol


def detect_regime(df: pd.DataFrame) -> dict:
    c = df["close"]
    if len(c) < 50:
        return {"regime": "unknown", "confidence": 0.2, "adx": 0.0,
                "vol_ratio": 1.0, "trend": 0.0, "trend_dir": 0.0}

    adx_df = adx_ind(df["high"], df["low"], c)
    adx_last = adx_df["adx"].iloc[-1]
    adx_v = float(adx_last) if not pd.isna(adx_last) else 0.0

    rv = realized_vol(c, 20).dropna()
    cur = float(rv.iloc[-1]) if len(rv) else 0.0
    med = float(rv.median()) if len(rv) else 0.0
    vol_ratio = cur / med if med else 1.0

    ef, es = float(ema(c, 20).iloc[-1]), float(ema(c, 50).iloc[-1])
    slope = (ef - es) / es if es else 0.0
    trend_dir = 1.0 if ef > es else -1.0

    if vol_ratio >= 2.5:
        regime, conf = "panic", 0.9
    elif vol_ratio >= 1.7:
        regime, conf = "volatile", 0.7
    elif adx_v >= 25:
        regime = "trending_up" if trend_dir > 0 else "trending_down"
        conf = float(min(0.9, 0.5 + adx_v / 100.0))
    else:
        regime, conf = "ranging", float(min(0.8, 0.4 + (25 - adx_v) / 50.0))

    return {"regime": regime, "confidence": round(conf, 2),
            "adx": round(adx_v, 1), "vol_ratio": round(vol_ratio, 2),
            "trend": round(slope, 4), "trend_dir": trend_dir}


# How much to trust each agent in each regime (directional voters only).
# Trend-followers get boosted in trends and trimmed in chop/stress; the desk
# turns conservative in volatile/panic regimes regardless of the signal.
_TREND_FOLLOWERS = {"Market Analyst", "Smart Money / SMC"}


def regime_weight_multiplier(agent_name: str, regime: str) -> float:
    if regime in ("trending_up", "trending_down"):
        return 1.30 if agent_name in _TREND_FOLLOWERS else 1.0
    if regime == "ranging":
        return 0.85 if agent_name in _TREND_FOLLOWERS else 1.05  # favour mean-reversion voices
    if regime == "volatile":
        return 0.6
    if regime == "panic":
        return 0.4
    return 1.0


# Tighten the confidence bar when the environment is dangerous, loosen it when a
# clean trend is in force. Positive = stricter (demand more conviction).
_REGIME_BAR_ADJ = {
    "trending_up": -0.07, "trending_down": -0.07,
    "ranging": 0.04, "volatile": 0.10, "panic": 0.18,
}


def dynamic_confidence_threshold(base: float, regime: str, regime_conf: float = 0.0) -> float:
    """Regime-adaptive confidence gate. Raises the bar in volatile/panic/ranging
    regimes (capital preservation) and lowers it under a confident strong trend,
    scaled by how sure the regime read is. Bounded [0.20, 0.85] so it never goes
    recklessly low or unreachably high."""
    adj = _REGIME_BAR_ADJ.get(regime, 0.0) * (0.5 + 0.5 * max(0.0, min(1.0, regime_conf)))
    return round(max(0.20, min(0.85, base + adj)), 3)
