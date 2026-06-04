"""Strategy library — deterministic, backtestable rules that plug into the
registry, the backtester and the StrategyEvolution ranker. Each returns a target
position series in [-1, 1] (no look-ahead; the backtester lags by a bar).

These are well-known published strategies, implemented honestly from indicators —
the AI learns which ones work by BACKTESTING + forward-testing them, not by magic.
"""
from __future__ import annotations

import pandas as pd

from ..indicators import adx, bollinger, donchian, ema, macd, rsi, vwap
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
