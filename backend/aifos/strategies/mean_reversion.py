"""Bollinger + RSI mean reversion. Fades stretched moves back toward the mean,
but only when NOT in a violent trend (guards against catching falling knives)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..indicators import bollinger, rsi, sma
from .base import Strategy, StrategySignal


class MeanReversionStrategy(Strategy):
    name = "mean_reversion"

    def __init__(self, window: int = 20, n_std: float = 2.0, rsi_lo: int = 30,
                 rsi_hi: int = 70, regime: int = 100, **kw) -> None:
        super().__init__(window=window, n_std=n_std, rsi_lo=rsi_lo,
                         rsi_hi=rsi_hi, regime=regime, **kw)
        self.window, self.n_std = window, n_std
        self.rsi_lo, self.rsi_hi, self.regime = rsi_lo, rsi_hi, regime

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        c = df["close"]
        bb = bollinger(c, self.window, self.n_std)
        r = rsi(c)
        regime_ma = sma(c, self.regime)
        # only fade within ~8% of the regime mean (avoid fighting strong trends)
        calm = (c.sub(regime_ma).abs() / regime_ma) < 0.08
        long = (c < bb["lower"]) & (r < self.rsi_lo) & calm
        short = (c > bb["upper"]) & (r > self.rsi_hi) & calm
        pos = pd.Series(0.0, index=c.index)
        pos[long] = 1.0
        pos[short] = -1.0
        # exit back to flat once price reclaims the mid band
        reclaimed = (c >= bb["mid"]) & (pos.shift(1).fillna(0) > 0)
        faded = (c <= bb["mid"]) & (pos.shift(1).fillna(0) < 0)
        pos[reclaimed | faded] = 0.0
        return pos.fillna(0.0)

    def latest_signal(self, df: pd.DataFrame) -> StrategySignal:
        c = df["close"]
        bb = bollinger(c, self.window, self.n_std)
        r = rsi(c).iloc[-1]
        price = c.iloc[-1]
        sig = self.generate_signals(df).iloc[-1]
        width = (bb["upper"].iloc[-1] - bb["lower"].iloc[-1]) / price if price else 0.0
        dist = abs(price - bb["mid"].iloc[-1]) / (width * price) if width else 0.0
        strength = float(np.clip(dist, 0, 1))
        side = "long (oversold)" if sig > 0 else "short (overbought)" if sig < 0 else "flat"
        rationale = f"price={price:.2f} vs band[{bb['lower'].iloc[-1]:.2f},{bb['upper'].iloc[-1]:.2f}], RSI={r:.0f} -> {side}"
        return StrategySignal(sig, strength, rationale, {"rsi": float(r)})
