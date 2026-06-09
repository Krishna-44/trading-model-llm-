"""Strategies ported from the freqtrade / jesse open-source ecosystems.

These are well-known TA strategy *patterns* that are staples of those two
communities (Ichimoku cloud, MACD signal-cross, Wilder's DMI/ADX, Donchian
"turtle" breakout, Heikin-Ashi trend, Hull-MA cross) but that AIFOS did not yet
have. They are re-implemented HONESTLY from our own indicators — not copied
code — so they obey the same no-look-ahead contract as the rest of the library
(the backtester lags positions one bar; nothing here reads a future value).

Why re-implement instead of bolting on freqtrade/jesse themselves: those are
complete standalone crypto bots with their own data + execution engines. Running
them would be 2–3 parallel systems, not one better one. The honest, high-value
move is to bring their best *ideas* into AIFOS's single forward record and let
the SAME Monte-Carlo + cost-stress gauntlet grade them. Most famous freqtrade
strategies are hyperopt-overfit and *should* fail that gauntlet — which is the
pipeline working, not a bug.

Provenance note: pattern lineage only. No GPL/strategy code is copied; each rule
is expressed from first principles against aifos.indicators.

GAUNTLET RESULT (scripts/grade_ported.py, 3yr ^NSEI/USDINR/BTC/RELIANCE basket):
    heikin_trend     +19.1%  pos 4/4  mc 2/4  cost 1/4  -> KEEP  (enabled, on watch)
    dmi_adx           +6.2%  pos 1/4  mc 1/4  cost 1/4  -> REVIEW (disabled)
    macd_cross        -3.5%  pos 1/4  mc 0/4  cost 1/4  -> DROP   (disabled)
    hull_cross        -6.8%  pos 1/4  mc 1/4  cost 1/4  -> DROP   (disabled)
    ichimoku_cloud    -7.3%  pos 1/4  mc 0/4  cost 0/4  -> DROP   (disabled)
    donchian_turtle   -7.4%  pos 1/4  mc 1/4  cost 1/4  -> DROP   (disabled)
Five of six rejected — the gauntlet refusing curve-fit/regime-lucky patterns is
the system working, not failing. Only heikin_trend is enabled (and only on watch).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..indicators import adx, donchian, ema, macd, stochastic
from ..indicators.extended import hull_ma, ichimoku
from .base import Strategy


def _pos(index, long, short) -> pd.Series:
    p = pd.Series(0.0, index=index)
    p[long] = 1.0
    p[short] = -1.0
    return p.fillna(0.0)


def _heikin_ashi(df: pd.DataFrame) -> pd.DataFrame:
    """Heikin-Ashi candles. HA_close is vectorised; HA_open is a linear
    recurrence (ha_open[i] = ½(ha_open[i-1] + ha_close[i-1])) so it's computed
    with a single pass. Uses only past/current bars — no look-ahead."""
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    ha_close = (o + h + l + c) / 4.0
    ha_open = np.empty(len(df), dtype=float)
    if len(df):
        ha_open[0] = float((o.iloc[0] + c.iloc[0]) / 2.0)
        cls = ha_close.values
        for i in range(1, len(df)):
            ha_open[i] = 0.5 * (ha_open[i - 1] + cls[i - 1])
    ha_open_s = pd.Series(ha_open, index=df.index)
    return pd.DataFrame({"ha_open": ha_open_s, "ha_close": ha_close})


# ── Ichimoku Kinkō Hyō cloud trend ────────────────────────────────────────────
class IchimokuCloudStrategy(Strategy):
    """Ichimoku cloud trend — a freqtrade staple. Long when price is ABOVE the
    cloud, Tenkan>Kijun, and the cloud itself is bullish (Senkou A>B); short the
    mirror. Deliberately ignores the Chikou span (it is a forward-shifted close =
    look-ahead) — we only use the cloud + conversion/base lines, all built from
    past bars."""
    name = "ichimoku_cloud"

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        c = df["close"]
        ic = ichimoku(df)
        long = (c > ic["cloud_top"]) & (ic["tenkan_sen"] > ic["kijun_sen"]) & ic["cloud_bullish"]
        short = (c < ic["cloud_bottom"]) & (ic["tenkan_sen"] < ic["kijun_sen"]) & (~ic["cloud_bullish"])
        return _pos(c.index, long.fillna(False), short.fillna(False))


# ── MACD signal-line cross with a trend filter ────────────────────────────────
class MacdCrossStrategy(Strategy):
    """The canonical freqtrade tutorial strategy: MACD vs its signal line, but
    gated by a long EMA so the cross is only taken WITH the higher-timeframe
    trend (raw MACD crosses whipsaw badly in chop). Holds long while the
    histogram is positive and price is above EMA200; mirror for shorts."""
    name = "macd_cross"

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        c = df["close"]
        m = macd(c)
        e200 = ema(c, 200)
        long = (m["hist"] > 0) & (c > e200)
        short = (m["hist"] < 0) & (c < e200)
        return _pos(c.index, long, short)


# ── Wilder DMI / ADX directional trend ────────────────────────────────────────
class DmiAdxStrategy(Strategy):
    """Wilder's Directional Movement system (DMI + ADX) — common in both
    ecosystems. Long when +DI>−DI and ADX confirms a real trend (≥25); short
    when −DI>+DI and ADX≥25. Stands flat in non-trending tape (low ADX), which
    is where DI crosses are noise."""
    name = "dmi_adx"

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        c = df["close"]
        a = adx(df["high"], df["low"], c)
        trending = a["adx"] >= 25
        long = (a["plus_di"] > a["minus_di"]) & trending
        short = (a["minus_di"] > a["plus_di"]) & trending
        return _pos(c.index, long, short)


# ── Classic Donchian "turtle" breakout (no volume filter) ─────────────────────
class DonchianTurtleStrategy(Strategy):
    """The original Turtle channel breakout: go long on a new N-bar high, short on
    a new N-bar low, and STAY in that direction until the opposite channel breaks
    ("always in the market"). Differs from AIFOS's breakout_volume by dropping the
    volume-surge confirmation — the pure trend-follower freqtrade/jesse users
    favour. N=20 entry by default."""
    name = "donchian_turtle"

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        c = df["close"]
        n = int(self.params.get("window", 20))
        dc = donchian(df["high"], df["low"], n)
        raw = pd.Series(np.nan, index=c.index)
        raw[c >= dc["upper"].shift(1)] = 1.0    # new N-bar high → long
        raw[c <= dc["lower"].shift(1)] = -1.0   # new N-bar low  → short
        return raw.ffill().fillna(0.0)          # carry last breakout (always-in)


# ── Heikin-Ashi smoothed trend ────────────────────────────────────────────────
class HeikinTrendStrategy(Strategy):
    """Heikin-Ashi trend-rider — hugely popular in the jesse/freqtrade communities
    for filtering noise. Requires TWO consecutive HA candles in the same direction
    (bullish body = ha_close>ha_open) aligned with the EMA50>EMA200 regime, so it
    only rides smoothed, confirmed trends.

    GAUNTLET (3yr basket): +19.1% avg, positive on ALL 4 markets, MC-robust 2/4 —
    the ONLY one of the six ported patterns to clear the KEEP bar (the other five
    DROPped/REVIEWed). HONEST CAVEAT: the edge is BTC-concentrated (+74% BTC vs
    +0/+2/+1% on NSEI/USDINR/RELIANCE) and survives 2× costs on only 1/4 markets —
    so it's enabled for paper forward-testing ON WATCH, not as a proven edge."""
    name = "heikin_trend"

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        c = df["close"]
        ha = _heikin_ashi(df)
        bull = ha["ha_close"] > ha["ha_open"]
        bear = ha["ha_close"] < ha["ha_open"]
        e50, e200 = ema(c, 50), ema(c, 200)
        long = bull & bull.shift(1).fillna(False) & (e50 > e200)
        short = bear & bear.shift(1).fillna(False) & (e50 < e200)
        return _pos(c.index, long, short)


# ── Hull MA fast/slow cross ───────────────────────────────────────────────────
class HullCrossStrategy(Strategy):
    """Hull Moving Average crossover. The Hull MA is far lower-lag than an EMA, so
    a fast/slow HMA cross turns faster than a classic MA cross while staying
    smooth. Long when HMA(fast)>HMA(slow) and the slow HMA is rising; mirror for
    shorts. Uses the loop's extended-indicator Hull MA."""
    name = "hull_cross"

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        c = df["close"]
        f = int(self.params.get("fast", 20))
        s = int(self.params.get("slow", 50))
        hf, hs = hull_ma(c, f), hull_ma(c, s)
        slow_up = hs > hs.shift(1)
        long = (hf > hs) & slow_up
        short = (hf < hs) & (~slow_up)
        return _pos(c.index, long.fillna(False), short.fillna(False))


PORTED: dict[str, type[Strategy]] = {
    "ichimoku_cloud": IchimokuCloudStrategy,
    "macd_cross": MacdCrossStrategy,
    "dmi_adx": DmiAdxStrategy,
    "donchian_turtle": DonchianTurtleStrategy,
    "heikin_trend": HeikinTrendStrategy,
    "hull_cross": HullCrossStrategy,
}

__all__ = [
    "IchimokuCloudStrategy", "MacdCrossStrategy", "DmiAdxStrategy",
    "DonchianTurtleStrategy", "HeikinTrendStrategy", "HullCrossStrategy",
    "PORTED",
]
