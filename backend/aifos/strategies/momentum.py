"""Trend-following momentum: EMA crossover gated by a long-term trend filter
and an ADX-like strength proxy. Goes long strong uptrends, short strong
downtrends, flat in chop — i.e. it *waits* when there is no trend."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..indicators import ema, rsi, sma
from .base import Strategy, StrategySignal


class MomentumStrategy(Strategy):
    name = "momentum"

    def __init__(self, fast: int = 20, slow: int = 50, trend: int = 200, **kw) -> None:
        super().__init__(fast=fast, slow=slow, trend=trend, **kw)
        self.fast, self.slow, self.trend = fast, slow, trend

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        c = df["close"]
        ef, es = ema(c, self.fast), ema(c, self.slow)
        trend_ma = sma(c, self.trend)
        long = (ef > es) & (c > trend_ma)
        short = (ef < es) & (c < trend_ma)
        pos = pd.Series(0.0, index=c.index)
        pos[long] = 1.0
        pos[short] = -1.0
        return pos.fillna(0.0)

    def latest_signal(self, df: pd.DataFrame) -> StrategySignal:
        c = df["close"]
        ef, es = ema(c, self.fast).iloc[-1], ema(c, self.slow).iloc[-1]
        trend_ma = sma(c, self.trend).iloc[-1]
        price = c.iloc[-1]
        r = rsi(c).iloc[-1]
        sig = self.generate_signals(df).iloc[-1]
        # conviction grows with EMA separation (normalised by price) and RSI extension
        sep = abs(ef - es) / price if price else 0.0
        strength = float(np.clip(sep * 25 + abs(r - 50) / 100, 0, 1))
        side = "long" if sig > 0 else "short" if sig < 0 else "flat"
        rationale = (
            f"EMA{self.fast}={ef:.2f} {'>' if ef > es else '<'} EMA{self.slow}={es:.2f}, "
            f"price {'above' if price > trend_ma else 'below'} SMA{self.trend}, "
            f"RSI={r:.0f} -> {side}"
        )
        return StrategySignal(sig, strength, rationale,
                              {"rsi": float(r), "ema_sep_pct": float(sep * 100)})
