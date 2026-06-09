"""Sector-rotation agent for Indian equities.

Reads relative strength of NIFTY sectoral indices (BANK / IT / METAL / AUTO /
FMCG / PHARMA / REALTY / ENERGY) over a lookback window. Leans bullish when
the candidate symbol's sector is in the top 2 by recent return; bearish when
in the bottom 2; neutral otherwise. Avoids fighting the dominant sectoral
flow even if a single-name setup looks attractive.

The mapping of stock-symbol → sector is hand-curated for major Indian names;
unknown symbols default to a "neutral" vote.

Implements aifos.agents.base.Agent.
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

# ─── Sector → NSE sectoral index symbol ─────────────────────────────────────
SECTOR_INDEX = {
    "bank":    "^NSEBANK",
    "it":      "^CNXIT",
    "metal":   "^CNXMETAL",
    "auto":    "^CNXAUTO",
    "fmcg":    "^CNXFMCG",
    "pharma":  "^CNXPHARMA",
    "realty":  "^CNXREALTY",
    "energy":  "^CNXENERGY",
}

# ─── Stock symbol → sector mapping (NIFTY 50 + frequent traders) ────────────
# yfinance NSE tickers end with .NS. Keep this in lower-case sector tags.
SYMBOL_SECTOR: dict[str, str] = {
    # Banks
    "HDFCBANK.NS": "bank", "ICICIBANK.NS": "bank", "SBIN.NS": "bank",
    "KOTAKBANK.NS": "bank", "AXISBANK.NS": "bank", "INDUSINDBK.NS": "bank",
    # IT
    "TCS.NS": "it", "INFY.NS": "it", "WIPRO.NS": "it", "HCLTECH.NS": "it",
    "TECHM.NS": "it", "LTIM.NS": "it",
    # Metals
    "TATASTEEL.NS": "metal", "JSWSTEEL.NS": "metal", "HINDALCO.NS": "metal",
    "VEDL.NS": "metal", "COALINDIA.NS": "metal",
    # Auto
    "MARUTI.NS": "auto", "TATAMOTORS.NS": "auto", "M&M.NS": "auto",
    "BAJAJ-AUTO.NS": "auto", "EICHERMOT.NS": "auto", "HEROMOTOCO.NS": "auto",
    # FMCG
    "HINDUNILVR.NS": "fmcg", "ITC.NS": "fmcg", "NESTLEIND.NS": "fmcg",
    "BRITANNIA.NS": "fmcg", "DABUR.NS": "fmcg",
    # Pharma
    "SUNPHARMA.NS": "pharma", "DRREDDY.NS": "pharma", "CIPLA.NS": "pharma",
    "DIVISLAB.NS": "pharma", "APOLLOHOSP.NS": "pharma",
    # Realty
    "DLF.NS": "realty", "GODREJPROP.NS": "realty", "OBEROIRLTY.NS": "realty",
    # Energy
    "RELIANCE.NS": "energy", "ONGC.NS": "energy", "POWERGRID.NS": "energy",
    "NTPC.NS": "energy", "ADANIPOWER.NS": "energy", "TATAPOWER.NS": "energy",
}


@dataclass(frozen=True)
class SectorScore:
    sector: str
    index_symbol: str
    return_pct: float
    rank: int                    # 1 = strongest, len(SECTOR_INDEX) = weakest


class SectorRotationAgent(Agent):
    name = "SectorRotation"
    weight = 0.8                # slightly below full — context, not driver

    def __init__(self, provider: "DataProvider | None" = None,
                 lookback_days: int = 20):
        self.provider = provider
        self.lookback_days = lookback_days

    def analyze(self, ctx: MarketContext) -> AgentOpinion:
        if self.provider is None:
            return self._neutral(ctx.symbol, "No data provider injected")

        sector = self._sector_of(ctx.symbol)
        if sector is None:
            return self._neutral(ctx.symbol, "Symbol not in sector map (treat as neutral context)")

        scores = self._rank_sectors()
        if not scores:
            return self._neutral(ctx.symbol, "Could not fetch sectoral data")

        rank_of = {s.sector: s.rank for s in scores}
        n = len(scores)
        r = rank_of.get(sector)
        if r is None:
            return self._neutral(ctx.symbol, f"Sector {sector!r} not scored")

        top_band = max(2, n // 4)        # top 2 (or top quartile)
        bot_band = max(2, n // 4)

        winners = ", ".join(f"{s.sector}({s.return_pct:+.1%})" for s in scores[:top_band])
        losers  = ", ".join(f"{s.sector}({s.return_pct:+.1%})" for s in scores[-bot_band:])

        if r <= top_band:
            stance = "bullish"
            confidence = 0.5 + 0.5 * (1 - (r - 1) / max(top_band - 1, 1))
            reasoning = (
                f"{ctx.symbol} is in {sector!r} which ranks {r}/{n} by "
                f"{self.lookback_days}d return. Top: {winners}."
            )
        elif r > n - bot_band:
            stance = "bearish"
            confidence = 0.5 + 0.5 * ((r - (n - bot_band)) / max(bot_band, 1))
            reasoning = (
                f"{ctx.symbol} is in {sector!r} which ranks {r}/{n} by "
                f"{self.lookback_days}d return — bottom band. Worst: {losers}."
            )
        else:
            stance = "neutral"
            confidence = 0.3
            reasoning = (
                f"{ctx.symbol} sector {sector!r} mid-pack (rank {r}/{n}). "
                f"No strong rotation signal."
            )

        return AgentOpinion(
            agent=self.name, stance=stance, confidence=float(min(1.0, confidence)),
            weight=self.weight, reasoning=reasoning,
            signals={
                "sector": sector, "rank": r, "n_sectors": n,
                "lookback_days": self.lookback_days,
                "top": [s.sector for s in scores[:top_band]],
                "bottom": [s.sector for s in scores[-bot_band:]],
            },
        )

    # ─── internals ──────────────────────────────────────────────────────
    def _sector_of(self, symbol: str) -> str | None:
        s = symbol.upper().strip()
        return SYMBOL_SECTOR.get(s)

    def _rank_sectors(self) -> list[SectorScore]:
        out: list[SectorScore] = []
        for sector, idx in SECTOR_INDEX.items():
            try:
                df = self.provider.history(idx, "1d")
                if df is None or len(df) < self.lookback_days + 2:
                    continue
                close = df["close"].astype(float)
                ret = (close.iloc[-1] / close.iloc[-self.lookback_days - 1]) - 1.0
                out.append(SectorScore(sector, idx, float(ret), 0))
            except Exception as e:  # noqa: BLE001
                log.debug("SectorRotation skip %s: %s", idx, e)
        if not out:
            return []
        out.sort(key=lambda s: s.return_pct, reverse=True)
        # Assign rank 1..n
        return [SectorScore(s.sector, s.index_symbol, s.return_pct, i + 1)
                for i, s in enumerate(out)]

    def _neutral(self, symbol: str, why: str) -> AgentOpinion:
        return AgentOpinion(
            agent=self.name, stance="neutral", confidence=0.0,
            weight=self.weight,
            reasoning=f"{symbol}: {why}",
            signals={"reason": why},
        )


__all__ = ["SectorRotationAgent", "SectorScore", "SECTOR_INDEX", "SYMBOL_SECTOR"]
