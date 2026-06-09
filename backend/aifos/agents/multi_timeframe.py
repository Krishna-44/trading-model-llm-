"""Multi-timeframe alignment agent.

Looks at price + EMAs across three timeframes (default 15m / 1h / 1d) and
votes bullish / bearish / neutral based on directional agreement. The point
isn't to be clever about any one timeframe — it's to refuse trades where the
timeframes DISAGREE.

A long on the 15m that fights the daily trend is the classic way small accounts
bleed. This agent flags that and lowers committee confidence accordingly.

Implements aifos.agents.base.Agent — drop into the committee like any other.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from .base import Agent, AgentOpinion, MarketContext

if TYPE_CHECKING:
    from ..data.providers import DataProvider

log = logging.getLogger(__name__)

DEFAULT_TIMEFRAMES = ("15m", "1h", "1d")


@dataclass(frozen=True)
class TimeframeView:
    timeframe: str
    direction: int        # +1 bull, -1 bear, 0 neutral
    strength: float       # 0-1
    close: float
    ema_fast: float
    ema_slow: float


class MultiTimeframeAgent(Agent):
    name = "MultiTimeframe"
    weight = 1.0          # full vote — adjust if you want it softer

    def __init__(self, provider: "DataProvider | None" = None,
                 timeframes: tuple[str, ...] = DEFAULT_TIMEFRAMES,
                 fast: int = 20, slow: int = 50):
        self.provider = provider     # if None, falls back to ctx.df only (single-timeframe degenerate)
        self.timeframes = timeframes
        self.fast = fast
        self.slow = slow

    def analyze(self, ctx: MarketContext) -> AgentOpinion:
        views = self._views(ctx)
        if not views:
            return AgentOpinion(
                agent=self.name, stance="neutral", confidence=0.0,
                weight=self.weight,
                reasoning=f"No usable history for {ctx.symbol} across {self.timeframes}",
                signals={"timeframes": list(self.timeframes), "views": 0},
            )

        longs  = sum(1 for v in views if v.direction == +1)
        shorts = sum(1 for v in views if v.direction == -1)
        flats  = sum(1 for v in views if v.direction ==  0)
        n = len(views)

        if longs > shorts and longs > flats:
            stance = "bullish"
            agreeing = [v for v in views if v.direction == 1]
            agreement = longs / n
        elif shorts > longs and shorts > flats:
            stance = "bearish"
            agreeing = [v for v in views if v.direction == -1]
            agreement = shorts / n
        else:
            stance = "neutral"
            agreeing = []
            agreement = max(longs, shorts) / n if n else 0.0

        avg_strength = float(np.mean([v.strength for v in agreeing])) if agreeing else 0.0
        completeness = len(views) / max(len(self.timeframes), 1)
        confidence = float(min(1.0, agreement * (0.4 + 0.6 * avg_strength) * completeness))

        breakdown = ", ".join(
            f"{v.timeframe}:{ {1:'↑',-1:'↓',0:'·'}[v.direction]}"
            for v in views
        )
        reasoning = (
            f"{self._summary(longs, shorts, flats, n)}. "
            f"Strength {avg_strength:.2f}, agreement {agreement:.0%}. [{breakdown}]"
        )
        return AgentOpinion(
            agent=self.name, stance=stance, confidence=confidence,
            weight=self.weight, reasoning=reasoning,
            signals={
                "longs": longs, "shorts": shorts, "neutrals": flats,
                "views": n, "timeframes": [v.timeframe for v in views],
                "avg_strength": round(avg_strength, 3),
            },
        )

    # ─── internals ──────────────────────────────────────────────────────
    def _views(self, ctx: MarketContext) -> list[TimeframeView]:
        # If a provider was injected we can fetch each timeframe; otherwise
        # we fall back to the single ctx.df (degenerate, single view).
        out: list[TimeframeView] = []
        if self.provider is not None:
            for tf in self.timeframes:
                v = self._view_from_provider(ctx.symbol, tf)
                if v: out.append(v)
        else:
            v = self._view_from_df(ctx.df, "ctx")
            if v: out.append(v)
        return out

    def _view_from_provider(self, symbol: str, tf: str) -> TimeframeView | None:
        try:
            df = self.provider.history(symbol, tf)
            v = self._view_from_df(df, tf)
            return v
        except Exception as e:  # noqa: BLE001
            log.warning("MultiTimeframe %s/%s failed: %s", symbol, tf, e)
            return None

    def _view_from_df(self, df: pd.DataFrame, tf: str) -> TimeframeView | None:
        if df is None or len(df) < self.slow + 5:
            return None
        close = df["close"]
        ema_f = float(close.ewm(span=self.fast, adjust=False, min_periods=self.fast).mean().iloc[-1])
        ema_s = float(close.ewm(span=self.slow, adjust=False, min_periods=self.slow).mean().iloc[-1])
        last = float(close.iloc[-1])
        if ema_f > ema_s and last > ema_s:
            direction = 1
        elif ema_f < ema_s and last < ema_s:
            direction = -1
        else:
            direction = 0
        spread = abs(ema_f - ema_s)
        rng = float(close.diff().abs().rolling(20).mean().iloc[-1] or 1e-9)
        strength = min(1.0, spread / max(rng * 5, 1e-9))
        return TimeframeView(tf, direction, float(strength), last, ema_f, ema_s)

    @staticmethod
    def _summary(longs: int, shorts: int, flats: int, n: int) -> str:
        if longs == n: return "All timeframes aligned bullish"
        if shorts == n: return "All timeframes aligned bearish"
        if longs > shorts: return f"{longs}/{n} timeframes bullish, {shorts} bearish, {flats} flat"
        if shorts > longs: return f"{shorts}/{n} timeframes bearish, {longs} bullish, {flats} flat"
        return f"Timeframes disagree ({longs}↑/{shorts}↓/{flats}·)"


__all__ = ["MultiTimeframeAgent", "TimeframeView", "DEFAULT_TIMEFRAMES"]
