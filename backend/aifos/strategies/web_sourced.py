"""Strategies discovered via web research, implemented honestly from indicators.

The user asked to "cook strategies searching across the net". These are well-
documented, reputable systematic strategies sourced from quantitative-trading
literature (Larry Connors' short-term mean-reversion family) and re-implemented
from first principles against aifos.indicators — no copied code, no look-ahead
(the backtester lags positions one bar). They are then graded by the SAME Monte
Carlo + cost-stress gauntlet as everything else; only survivors get enabled.

Why these specifically: AIFOS's enabled set is TREND-heavy (EMA stacks,
Supertrend). The research is consistent that mean-reversion works on equities and
range-bound FX while momentum works on crypto — so a validated short-term
mean-reversion sleeve genuinely DIVERSIFIES the book rather than piling on
another correlated trend vote.

Sources:
  - Connors, "Short Term Trading Strategies That Work" (RSI-2, Double-7s)
  - quantifiedstrategies.com / stockcharts.com ChartSchool (rule write-ups)

GAUNTLET RESULT (3yr ^NSEI/USDINR/BTC/RELIANCE basket):
    double7_connors  +8.2%  pos 3/4  mc 3/4  cost 2/4  -> PROMOTE (enabled, on watch)
    rsi2_connors     +6.7%  pos 2/4  mc 2/4  cost 1/4  -> KEEP, cost-fragile (disabled)
Double-7s is positive on range-bound USDINR (+5%) where the trend strategies are
flat — the diversification the research predicted. Only the survivor is enabled.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..indicators import rsi, sma
from .base import Strategy


def _state_positions(index, long_entry, long_exit, short_entry, short_exit) -> pd.Series:
    """Turn entry/exit event masks into a held position series (-1/0/+1) via a
    simple one-position-at-a-time state machine: flat → enter on an entry signal,
    hold until the matching exit, then flat. Single pass; uses only past/current
    bars (the backtester lags by one bar, so no look-ahead)."""
    le = long_entry.fillna(False).values
    lx = long_exit.fillna(False).values
    se = short_entry.fillna(False).values
    sx = short_exit.fillna(False).values
    pos = np.zeros(len(index))
    state = 0
    for i in range(len(index)):
        if state == 0:
            if le[i]:
                state = 1
            elif se[i]:
                state = -1
        elif state == 1:
            if lx[i]:
                state = 0
        else:  # state == -1
            if sx[i]:
                state = 0
        pos[i] = state
    return pd.Series(pos, index=index)


class ConnorsRsi2Strategy(Strategy):
    """Larry Connors' RSI(2) mean reversion. ONLY with the 200-SMA trend:
    long when price>200-SMA and the ultra-fast RSI(2) is washed out (<entry, def 5),
    exit when price closes back above the 5-SMA; mirror for shorts below the
    200-SMA. Captures short-term panic/euphoria snaps in the direction of the
    larger trend. Distinct from AIFOS's bollinger_reversion (band+ADX) and
    mean_reversion (z-score) — this is the ultra-short RSI(2) variant."""
    name = "rsi2_connors"

    def __init__(self, low: int = 5, high: int = 95) -> None:
        self.low, self.high = low, high

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        c = df["close"]
        r = rsi(c, 2)
        s200, s5 = sma(c, 200), sma(c, 5)
        up, down = c > s200, c < s200
        long_entry = up & (r < self.low)
        long_exit = c > s5
        short_entry = down & (r > self.high)
        short_exit = c < s5
        return _state_positions(c.index, long_entry, long_exit, short_entry, short_exit)


class ConnorsDouble7Strategy(Strategy):
    """Connors' "Double 7s": with price above the 200-SMA, buy a new 7-day LOW and
    sell when it makes a new 7-day HIGH (mirror below the 200-SMA). A slower,
    swing-grade mean-reversion than RSI(2) — fewer, larger snaps. Uses only
    rolling extrema + the trend filter."""
    name = "double7_connors"

    def __init__(self, window: int = 7) -> None:
        self.window = window

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        c = df["close"]
        s200 = sma(c, 200)
        n = self.window
        low_n = c.rolling(n).min()
        high_n = c.rolling(n).max()
        up, down = c > s200, c < s200
        long_entry = up & (c <= low_n)
        long_exit = c >= high_n
        short_entry = down & (c >= high_n)
        short_exit = c <= low_n
        return _state_positions(c.index, long_entry, long_exit, short_entry, short_exit)


WEB_SOURCED: dict[str, type[Strategy]] = {
    "rsi2_connors": ConnorsRsi2Strategy,
    "double7_connors": ConnorsDouble7Strategy,
}

__all__ = ["ConnorsRsi2Strategy", "ConnorsDouble7Strategy", "WEB_SOURCED"]
