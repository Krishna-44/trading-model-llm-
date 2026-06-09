"""Extended technical indicators — Ichimoku, Aroon, Hull MA, Volume Profile.

These are NOT bundled in indicators/core.py so the core stays focused on the
hot path. They're available for the Strategy Evolution agent to use when
exploring the strategy space. All functions follow the same shape as core.py:
take a DataFrame (or Series) and return a Series / DataFrame indexed the same
way as the input.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = ["ichimoku", "aroon", "hull_ma", "volume_profile", "vwap_anchored"]


def ichimoku(df: pd.DataFrame, tenkan: int = 9, kijun: int = 26,
             senkou_b: int = 52, displacement: int = 26) -> pd.DataFrame:
    """Ichimoku Kinkō Hyō — five-line trend / support / cloud system.

    Returns columns:
      tenkan_sen     — short-term momentum line (mid-high/low over `tenkan`)
      kijun_sen      — medium-term equilibrium (mid-high/low over `kijun`)
      senkou_a       — leading span A — average of tenkan + kijun, shifted +displacement
      senkou_b       — leading span B — mid-high/low over senkou_b period, shifted +displacement
      chikou_span    — lagging close, shifted -displacement
      cloud_top      — max(senkou_a, senkou_b)
      cloud_bottom   — min(senkou_a, senkou_b)
      cloud_bullish  — bool: senkou_a > senkou_b at current bar
    """
    high = df["high"]; low = df["low"]; close = df["close"]

    def mid(period: int) -> pd.Series:
        return (high.rolling(period).max() + low.rolling(period).min()) / 2.0

    tenkan_sen = mid(tenkan)
    kijun_sen  = mid(kijun)
    senkou_a   = ((tenkan_sen + kijun_sen) / 2.0).shift(displacement)
    senkou_b_s = mid(senkou_b).shift(displacement)
    chikou_s   = close.shift(-displacement)

    cloud_top    = pd.concat([senkou_a, senkou_b_s], axis=1).max(axis=1)
    cloud_bottom = pd.concat([senkou_a, senkou_b_s], axis=1).min(axis=1)
    cloud_bull   = (senkou_a > senkou_b_s)

    return pd.DataFrame({
        "tenkan_sen": tenkan_sen,
        "kijun_sen":  kijun_sen,
        "senkou_a":   senkou_a,
        "senkou_b":   senkou_b_s,
        "chikou_span": chikou_s,
        "cloud_top":    cloud_top,
        "cloud_bottom": cloud_bottom,
        "cloud_bullish": cloud_bull,
    })


def aroon(df: pd.DataFrame, period: int = 25) -> pd.DataFrame:
    """Aroon Up / Aroon Down / Aroon oscillator.

    Aroon Up   = 100 * (period - bars-since-period-high) / period
    Aroon Down = 100 * (period - bars-since-period-low) / period
    Oscillator = Aroon Up - Aroon Down (range [-100, +100])

    Strong trend when |Oscillator| > 50, with sign giving direction.
    """
    high = df["high"]; low = df["low"]

    def _bars_since_max(s: pd.Series, n: int) -> pd.Series:
        idx = s.rolling(n + 1).apply(lambda w: float(n - np.argmax(w[::-1])), raw=True)
        return idx

    def _bars_since_min(s: pd.Series, n: int) -> pd.Series:
        idx = s.rolling(n + 1).apply(lambda w: float(n - np.argmin(w[::-1])), raw=True)
        return idx

    bs_high = _bars_since_max(high, period)
    bs_low  = _bars_since_min(low,  period)

    aroon_up   = 100.0 * (period - bs_high) / period
    aroon_down = 100.0 * (period - bs_low)  / period
    osc        = aroon_up - aroon_down

    return pd.DataFrame({"aroon_up": aroon_up, "aroon_down": aroon_down, "aroon_osc": osc})


def hull_ma(series: pd.Series, period: int = 20) -> pd.Series:
    """Hull Moving Average — fast, low-lag MA.

        HMA(n) = WMA(2*WMA(n/2) - WMA(n), sqrt(n))
    """
    if period < 2:
        raise ValueError("Hull MA period must be >= 2")

    def _wma(s: pd.Series, n: int) -> pd.Series:
        w = np.arange(1, n + 1, dtype=float)
        return s.rolling(n).apply(lambda x: float(np.dot(x, w) / w.sum()), raw=True)

    half = max(1, period // 2)
    sqrt_p = max(1, int(round(np.sqrt(period))))
    inner = 2 * _wma(series, half) - _wma(series, period)
    return _wma(inner, sqrt_p)


def volume_profile(df: pd.DataFrame, bins: int = 24, value_area_pct: float = 0.70) -> dict:
    """Discrete volume profile over the given dataframe's range.

    Returns:
      buckets        — list of (price_low, price_high, volume) tuples, low→high
      poc            — Price Of Control (price of highest-volume bucket)
      value_area_low — lower bound containing `value_area_pct` of volume around POC
      value_area_high — upper bound of same
      total_volume   — sum of volume in the window

    Use it to see where buyers / sellers were stuck (high volume zones) — those
    levels often act as support / resistance going forward.
    """
    if df.empty:
        return {"buckets": [], "poc": None, "value_area_low": None,
                "value_area_high": None, "total_volume": 0.0}

    lo, hi = float(df["low"].min()), float(df["high"].max())
    if hi <= lo:
        return {"buckets": [], "poc": None, "value_area_low": lo,
                "value_area_high": hi, "total_volume": float(df["volume"].sum())}

    edges = np.linspace(lo, hi, bins + 1)
    vols = np.zeros(bins, dtype=float)

    # Spread each bar's volume across the buckets it touches, weighted by overlap.
    for _, row in df.iterrows():
        bar_lo, bar_hi, bar_v = float(row["low"]), float(row["high"]), float(row["volume"])
        if bar_hi <= bar_lo or bar_v <= 0:
            continue
        # Vectorised overlap into the bucket edges.
        bucket_los = edges[:-1]
        bucket_his = edges[1:]
        overlap = np.clip(np.minimum(bucket_his, bar_hi) - np.maximum(bucket_los, bar_lo), 0, None)
        bar_range = bar_hi - bar_lo
        if bar_range <= 0:
            continue
        vols += bar_v * overlap / bar_range

    total = float(vols.sum())
    poc_idx = int(np.argmax(vols))
    poc = float((edges[poc_idx] + edges[poc_idx + 1]) / 2)

    # Value area: expand outward from POC until cumulative volume covers value_area_pct.
    target = total * value_area_pct
    cum = vols[poc_idx]
    lo_i = hi_i = poc_idx
    while cum < target and (lo_i > 0 or hi_i < bins - 1):
        left  = vols[lo_i - 1] if lo_i > 0 else -1
        right = vols[hi_i + 1] if hi_i < bins - 1 else -1
        if left >= right:
            if lo_i > 0:
                lo_i -= 1; cum += vols[lo_i]
            else:
                hi_i += 1; cum += vols[hi_i]
        else:
            if hi_i < bins - 1:
                hi_i += 1; cum += vols[hi_i]
            else:
                lo_i -= 1; cum += vols[lo_i]

    return {
        "buckets": [(float(edges[i]), float(edges[i + 1]), float(vols[i])) for i in range(bins)],
        "poc": poc,
        "value_area_low":  float(edges[lo_i]),
        "value_area_high": float(edges[hi_i + 1]),
        "total_volume":    total,
    }


def vwap_anchored(df: pd.DataFrame, anchor_index: int = 0) -> pd.Series:
    """Anchored VWAP — VWAP computed cumulatively starting from `anchor_index`.

    Useful for measuring price vs. average traded price since a specific event
    (earnings, breakout, session open). Reset point is the anchor.
    """
    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    cum_vp = (typical.iloc[anchor_index:] * df["volume"].iloc[anchor_index:]).cumsum()
    cum_v  = df["volume"].iloc[anchor_index:].cumsum().replace(0, np.nan)
    out = pd.Series(index=df.index, dtype=float)
    out.iloc[anchor_index:] = cum_vp / cum_v
    return out
