"""Strategy library — deterministic, backtestable rules that plug into the
registry, the backtester and the StrategyEvolution ranker. Each returns a target
position series in [-1, 1] (no look-ahead; the backtester lags by a bar).

These are well-known published strategies, implemented honestly from indicators —
the AI learns which ones work by BACKTESTING + forward-testing them, not by magic.
"""
from __future__ import annotations

import pandas as pd

from ..indicators import adx, atr, bollinger, donchian, ema, keltner, macd, rsi, supertrend, vwap
from .base import Strategy


def _pos(index, long, short) -> pd.Series:
    p = pd.Series(0.0, index=index)
    p[long] = 1.0
    p[short] = -1.0
    return p.fillna(0.0)


class VwapTrendStrategy(Strategy):
    """Institutional VWAP trend — long above rising VWAP, short below falling VWAP."""
    name = "vwap_trend"

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        c = df["close"]
        vw = vwap(df["high"], df["low"], c, df["volume"], 20)
        e20 = ema(c, 20)
        return _pos(c.index, (c > vw) & (e20 > e20.shift(1)), (c < vw) & (e20 < e20.shift(1)))


class EmaTrendStrategy(Strategy):
    """EMA 20/50/200 stacked-alignment trend continuation (swing)."""
    name = "ema_trend"

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        c = df["close"]
        e20, e50, e200 = ema(c, 20), ema(c, 50), ema(c, 200)
        return _pos(c.index, (e20 > e50) & (e50 > e200), (e20 < e50) & (e50 < e200))


class RsiMacdStrategy(Strategy):
    """RSI momentum-zone + MACD histogram confirmation."""
    name = "rsi_macd"

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        c = df["close"]
        r = rsi(c)
        hist = macd(c)["hist"]
        return _pos(c.index, (r > 52) & (hist > 0), (r < 48) & (hist < 0))


class BollingerReversionStrategy(Strategy):
    """Mean-reversion: fade the outer Bollinger band when RSI is extreme and the
    market is range-bound (low ADX). Stands aside in strong trends."""
    name = "bollinger_reversion"

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        c = df["close"]
        bb = bollinger(c, 20, 2.0)
        r = rsi(c)
        ranging = adx(df["high"], df["low"], c)["adx"] < 25
        long = (c <= bb["lower"]) & (r < 35) & ranging
        short = (c >= bb["upper"]) & (r > 65) & ranging
        return _pos(c.index, long, short)


class BreakoutVolumeStrategy(Strategy):
    """Donchian breakout confirmed by a volume surge (momentum / volatility expansion)."""
    name = "breakout_volume"

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        c = df["close"]
        dc = donchian(df["high"], df["low"], 20)
        vol = df["volume"]
        surge = vol > 1.5 * vol.rolling(20, min_periods=5).mean()
        long = (c >= dc["upper"].shift(1)) & surge
        short = (c <= dc["lower"].shift(1)) & surge
        return _pos(c.index, long, short)


class SupertrendStrategy(Strategy):
    """Supertrend (ATR-band) trend-follower with a trend-strength filter (ADX>=20),
    so it stays out of chop where Supertrend whipsaws."""
    name = "supertrend"

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        c = df["close"]
        st = supertrend(df["high"], df["low"], c, window=10, mult=3.0)
        a = adx(df["high"], df["low"], c)["adx"]
        trending = a >= 20
        return _pos(c.index, (st["direction"] > 0) & trending, (st["direction"] < 0) & trending)


class KeltnerSqueezeStrategy(Strategy):
    """Keltner-channel squeeze breakout. Bollinger inside Keltner = volatility
    contraction; trade the FIRST close outside the Keltner band in either direction
    (volatility expansion). Honest, published TTM-squeeze structure."""
    name = "keltner_squeeze"

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        c = df["close"]
        bb = bollinger(c, 20, 2.0)
        kc = keltner(df["high"], df["low"], c, 20, 1.5)
        squeezed = (bb["lower"] >= kc["lower"]) & (bb["upper"] <= kc["upper"])
        was_squeezed = squeezed.shift(1).fillna(False)
        long = was_squeezed & (c > kc["upper"])
        short = was_squeezed & (c < kc["lower"])
        return _pos(c.index, long, short)


class AtrMomentumStrategy(Strategy):
    """Volatility-expansion momentum: enter on a price move ≥ 1.5×ATR(14) in the
    direction of the EMA50 trend, with a 200-MA regime filter. Captures impulsive
    moves out of consolidation while filtering out aimless drift."""
    name = "atr_momentum"

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        c = df["close"]
        a = atr(df["high"], df["low"], c, 14)
        bar_move = c - c.shift(1)
        e50, e200 = ema(c, 50), ema(c, 200)
        long = (bar_move >= 1.5 * a) & (e50 > e200)
        short = (bar_move <= -1.5 * a) & (e50 < e200)
        return _pos(c.index, long, short)


# ── PROMOTED from the cooking discovery loop (validated MC-robust across markets) ──
class EmaTrendFastStrategy(Strategy):
    """Faster EMA trend (10/30/100). Cooking discovered this beats the default
    20/50/200 across the multi-market basket (+22% avg, MC-robust 2/4, positive 3/4).
    Captures trends earlier; promoted to forward-test it live."""
    name = "ema_trend_fast"

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        c = df["close"]
        e10, e30, e100 = ema(c, 10), ema(c, 30), ema(c, 100)
        return _pos(c.index, (e10 > e30) & (e30 > e100), (e10 < e30) & (e30 < e100))


class SupertrendFastStrategy(Strategy):
    """Tighter Supertrend (7-period ATR, 4× band, ADX≥15). Cooking found this
    positive on ALL 4 basket markets (+14.7% avg, MC-robust 2/4) — the broadest-
    robust new variant. Promoted to forward-test it live."""
    name = "supertrend_fast"

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        c = df["close"]
        st = supertrend(df["high"], df["low"], c, window=7, mult=4.0)
        a = adx(df["high"], df["low"], c)["adx"]
        ok = a >= 15
        return _pos(c.index, (st["direction"] > 0) & ok, (st["direction"] < 0) & ok)
