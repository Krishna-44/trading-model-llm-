"""Directional / informational agents.

MarketAnalyst is the primary voter (multi-indicator confluence + the strategy
chosen by the StrategyEvolution agent). Sentiment/News/Macro are supporting
voices — deliberately honest about what they can and cannot see without paid
feeds, and Macro carries a volatility kill (veto on chaos)."""
from __future__ import annotations

import numpy as np

from ..indicators import ema, macd, realized_vol, rsi, sma
from ..strategies import build_strategy
from .base import Agent, AgentOpinion, MarketContext


def _stance(net: float, dead: float = 0.08) -> str:
    if net > dead:
        return "bullish"
    if net < -dead:
        return "bearish"
    return "neutral"


class MarketAnalystAgent(Agent):
    name = "Market Analyst"
    weight = 1.0

    def analyze(self, ctx: MarketContext) -> AgentOpinion:
        df = ctx.df
        c = df["close"]
        if len(c) < 60:
            return AgentOpinion(self.name, "neutral", 0.2, self.weight,
                                "insufficient history for a confident read")
        ef, es = ema(c, 20).iloc[-1], ema(c, 50).iloc[-1]
        trend200 = sma(c, 200).iloc[-1] if len(c) >= 200 else sma(c, 100).iloc[-1]
        macd_hist = macd(c)["hist"].iloc[-1]
        r = rsi(c).iloc[-1]
        price = float(c.iloc[-1])

        trend_dir = 1.0 if ef > es else -1.0
        regime_dir = 1.0 if price > trend200 else -1.0
        macd_dir = float(np.sign(macd_hist))
        rsi_dir = 1.0 if r > 55 else -1.0 if r < 45 else 0.0

        # confluence of independent reads
        net = 0.30 * trend_dir + 0.25 * regime_dir + 0.25 * macd_dir + 0.20 * rsi_dir

        # blend the evolution-selected strategy's own signal
        strat_name = ctx.extra.get("strategy_name", "momentum")
        strat = build_strategy(strat_name)
        ssig = strat.latest_signal(df)
        net = 0.6 * net + 0.4 * (np.sign(ssig.target_position) * ssig.strength)

        stance = _stance(net)
        confidence = float(np.clip(abs(net), 0.0, 0.95))
        reasoning = (
            f"Confluence: trend EMA20{'>' if ef > es else '<'}EMA50, "
            f"price {'above' if price > trend200 else 'below'} long MA, "
            f"MACD {'+' if macd_hist > 0 else '-'}, RSI {r:.0f}. "
            f"Strategy[{strat_name}]: {ssig.rationale}"
        )
        return AgentOpinion(self.name, stance, confidence, self.weight, reasoning,
                            {"rsi": round(float(r), 1), "macd_hist": round(float(macd_hist), 4),
                             "net_score": round(float(net), 3), "strategy": strat_name})


class SentimentAgent(Agent):
    name = "Sentiment Analyst"
    weight = 0.4

    def analyze(self, ctx: MarketContext) -> AgentOpinion:
        c = ctx.df["close"]
        if len(c) < 25:
            return AgentOpinion(self.name, "neutral", 0.2, self.weight,
                                "not enough data for sentiment proxy")
        ret5 = float(c.iloc[-1] / c.iloc[-6] - 1)
        hi20 = float(c.iloc[-20:].max())
        from_high = float(c.iloc[-1] / hi20 - 1)
        r = float(rsi(c).iloc[-1])
        # price-action sentiment proxy (NO live social/news feed configured)
        score = np.tanh(ret5 * 8) * 0.6 + np.tanh(from_high * 8) * 0.2 + ((r - 50) / 50) * 0.2
        stance = _stance(float(score))
        return AgentOpinion(
            self.name, stance, float(np.clip(abs(score), 0, 0.7)), self.weight,
            f"Price-action sentiment proxy (no live social feed): 5-bar {ret5:+.2%}, "
            f"{from_high:+.2%} vs 20-bar high, RSI {r:.0f}",
            {"ret5": round(ret5, 4), "from_high": round(from_high, 4)},
        )


class NewsAgent(Agent):
    name = "News Intelligence"
    weight = 0.2

    def analyze(self, ctx: MarketContext) -> AgentOpinion:
        # real Yahoo headlines for equities/crypto; abstains (weight 0) elsewhere
        if ctx.asset_class not in ("equity", "crypto"):
            return AgentOpinion(self.name, "neutral", 0.0, 0.0,
                                "no headline feed for this asset class — abstaining", {"feed": "yahoo"})
        from ..news.intelligence import news_intelligence
        try:
            ni = news_intelligence(ctx.symbol, limit=8)
        except Exception:  # noqa: BLE001
            ni = {"count": 0}
        if not ni.get("count"):
            return AgentOpinion(self.name, "neutral", 0.0, 0.0,
                                "no live headlines — abstaining", {"feed": "yahoo"})
        agg = ni["aggregate"]
        conf = min(0.7, 0.3 + 0.08 * (agg["bullish"] + agg["bearish"]) + agg["avg_impact"] * 0.3)
        reasoning = (f"{ni['count']} headlines: {agg['bullish']}↑/{agg['bearish']}↓, "
                     f"avg impact {agg['avg_impact']} -> {agg['sentiment']}")
        return AgentOpinion(self.name, agg["sentiment"], round(conf, 2), self.weight, reasoning,
                            {"net": agg["net"], "avg_impact": agg["avg_impact"]})


class MacroAgent(Agent):
    name = "Macro / Regime"
    weight = 0.5

    def analyze(self, ctx: MarketContext) -> AgentOpinion:
        c = ctx.df["close"]
        rv = realized_vol(c, 20).dropna()
        if len(rv) < 30:
            return AgentOpinion(self.name, "neutral", 0.4, self.weight,
                                "insufficient data for regime read")
        cur = float(rv.iloc[-1])
        med = float(rv.median())
        ratio = cur / med if med else 1.0
        # volatility kill: stand aside in a vol spike (black-swan guard)
        if ratio > 2.5:
            return AgentOpinion(
                self.name, "neutral", 0.9, self.weight,
                f"VOLATILITY KILL: realized vol {cur:.0%} is {ratio:.1f}x its median "
                f"{med:.0%} — regime unstable, stand aside.",
                {"realized_vol": round(cur, 3), "vol_ratio": round(ratio, 2)}, veto=True,
            )
        reg = ctx.extra.get("regime", {})
        label = reg.get("regime", "calm" if ratio < 1.2 else "elevated")
        return AgentOpinion(
            self.name, "neutral", 0.5 if ratio < 1.2 else 0.35, self.weight,
            f"Regime: {label} (ADX {reg.get('adx', '?')}, realized vol {cur:.0%}, "
            f"{ratio:.1f}x median).",
            {"realized_vol": round(cur, 3), "vol_ratio": round(ratio, 2),
             "regime": label, "adx": reg.get("adx")},
        )


class SmartMoneyAgent(Agent):
    """Smart Money Concepts (SMC/ICT): market structure, order blocks, FVGs,
    premium/discount and liquidity sweeps — deterministic price geometry."""
    name = "Smart Money / SMC"
    weight = 1.0

    def analyze(self, ctx: MarketContext) -> AgentOpinion:
        smc = ctx.extra.get("smc")
        if smc is None:
            from ..indicators.smc import smc_signals
            smc = smc_signals(ctx.df)
        score = float(smc.get("score", 0.0))
        comp = smc.get("components", {})
        struct = comp.get("structure", {})
        zone = comp.get("zone", {})
        return AgentOpinion(
            self.name, smc.get("bias", "neutral"),
            float(np.clip(abs(score) * 1.2, 0.0, 0.9)), self.weight,
            f"SMC: {smc.get('reasoning', 'no clear edge')}.",
            {"score": score, "event": struct.get("event"), "zone": zone.get("zone"),
             "swing_low": struct.get("last_swing_low"),
             "swing_high": struct.get("last_swing_high")},
        )


class CandlestickAgent(Agent):
    """Classic candlestick patterns — a light, informational read of price psychology."""
    name = "Candlestick"
    weight = 0.3

    def analyze(self, ctx: MarketContext) -> AgentOpinion:
        cr = ctx.extra.get("candles")
        if cr is None:
            from ..indicators.candles import candle_read
            cr = candle_read(ctx.df)
        score = float(cr.get("score", 0.0))
        return AgentOpinion(
            self.name, cr.get("bias", "neutral"),
            float(np.clip(abs(score), 0.0, 0.7)), self.weight,
            f"Candles: {cr.get('summary', 'no pattern')}.",
            {"patterns": [p["name"] for p in cr.get("patterns", [])], "score": score},
        )
