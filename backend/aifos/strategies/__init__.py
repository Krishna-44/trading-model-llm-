from .base import Strategy, StrategySignal
from .library import (
    AtrMomentumStrategy,
    BollingerReversionStrategy,
    BreakoutVolumeStrategy,
    EmaTrendFastStrategy,
    EmaTrendFibStrategy,
    EmaTrendStrategy,
    KeltnerSqueezeStrategy,
    RsiMacdStrategy,
    SupertrendFastStrategy,
    SupertrendStrategy,
    VwapTrendStrategy,
)
from .mean_reversion import MeanReversionStrategy
from .momentum import MomentumStrategy
from .ported import (
    DmiAdxStrategy,
    DonchianTurtleStrategy,
    HeikinTrendStrategy,
    HullCrossStrategy,
    IchimokuCloudStrategy,
    MacdCrossStrategy,
)
from .web_sourced import ConnorsDouble7Strategy, ConnorsRsi2Strategy

REGISTRY: dict[str, type[Strategy]] = {
    "momentum": MomentumStrategy,
    "mean_reversion": MeanReversionStrategy,
    "vwap_trend": VwapTrendStrategy,
    "ema_trend": EmaTrendStrategy,
    "rsi_macd": RsiMacdStrategy,
    "bollinger_reversion": BollingerReversionStrategy,
    "breakout_volume": BreakoutVolumeStrategy,
    "supertrend": SupertrendStrategy,
    "keltner_squeeze": KeltnerSqueezeStrategy,
    "atr_momentum": AtrMomentumStrategy,
    "ema_trend_fast": EmaTrendFastStrategy,       # promoted from cooking
    "supertrend_fast": SupertrendFastStrategy,    # promoted from cooking
    "ema_trend_fib": EmaTrendFibStrategy,         # promoted from cooking (most MC-robust, 3/4)
    # ── ported from the freqtrade / jesse ecosystems (graded by the gauntlet) ──
    "ichimoku_cloud": IchimokuCloudStrategy,
    "macd_cross": MacdCrossStrategy,
    "dmi_adx": DmiAdxStrategy,
    "donchian_turtle": DonchianTurtleStrategy,
    "heikin_trend": HeikinTrendStrategy,
    "hull_cross": HullCrossStrategy,
    # ── discovered via web research (Connors mean-reversion); gauntlet-graded ──
    "rsi2_connors": ConnorsRsi2Strategy,
    "double7_connors": ConnorsDouble7Strategy,
}

# Human-facing descriptions for the strategy marketplace.
STRATEGY_INFO = {
    "momentum": {"label": "Momentum Trend", "bias": "trend", "best_for": "trending markets",
                 "desc": "EMA20/50 crossover gated by a 200-MA trend filter — rides strong trends, waits in chop."},
    "mean_reversion": {"label": "Mean Reversion", "bias": "range", "best_for": "range-bound markets",
                       "desc": "Fades z-score extremes back toward the mean — for sideways conditions."},
    "vwap_trend": {"label": "VWAP Institutional Trend", "bias": "trend", "best_for": "intraday trends",
                   "desc": "Long above rising VWAP, short below falling VWAP — institutional intraday bias."},
    "ema_trend": {"label": "EMA Trend Continuation", "bias": "trend", "best_for": "swing trends",
                  "desc": "EMA 20>50>200 stacked alignment — clean trend continuation for swings."},
    "rsi_macd": {"label": "RSI + MACD Momentum", "bias": "momentum", "best_for": "equities / crypto / forex",
                 "desc": "RSI momentum zone confirmed by the MACD histogram. Avoid low-vol chop."},
    "bollinger_reversion": {"label": "Bollinger Mean Reversion", "bias": "range", "best_for": "range-bound markets",
                            "desc": "Fade the outer Bollinger band on an RSI extreme while ADX is low (ranging)."},
    "breakout_volume": {"label": "Breakout + Volume", "bias": "breakout", "best_for": "momentum / volatility expansion",
                        "desc": "Donchian breakout confirmed by a volume surge — momentum & volatility plays."},
    "supertrend": {"label": "Supertrend (ATR)", "bias": "trend", "best_for": "trending markets",
                   "desc": "Classic ATR-band Supertrend, gated by ADX≥20 to skip chop where it whipsaws."},
    "keltner_squeeze": {"label": "Keltner Squeeze", "bias": "breakout", "best_for": "volatility expansion",
                        "desc": "TTM-style squeeze: BBands inside Keltner = compression; trade the first close outside Keltner."},
    "atr_momentum": {"label": "ATR Momentum", "bias": "momentum", "best_for": "impulsive moves",
                     "desc": "Enter on ≥1.5×ATR bar move with EMA50/200 regime alignment — captures volatility expansion."},
    "ema_trend_fast": {"label": "EMA Trend (fast 10/30/100)", "bias": "trend", "best_for": "trending markets",
                       "desc": "Cooking-discovered fast EMA stack — beat the default 20/50/200 across markets. Forward-testing live."},
    "supertrend_fast": {"label": "Supertrend (fast 7/4)", "bias": "trend", "best_for": "trending markets",
                        "desc": "Cooking-discovered tight Supertrend (ADX≥15) — positive on all 4 basket markets. Forward-testing live."},
    "ema_trend_fib": {"label": "EMA Trend (Fib 13/34/89)", "bias": "trend", "best_for": "trending markets",
                      "desc": "Cooking's most MC-robust discovery (3/4 markets over 213 rounds, +16.5% avg). Fibonacci-spaced EMA stack. Forward-testing live."},
    # ── ported from freqtrade / jesse (pattern lineage only; re-implemented honestly) ──
    "ichimoku_cloud": {"label": "Ichimoku Cloud", "bias": "trend", "best_for": "sustained trends", "source": "freqtrade",
                       "desc": "Price above/below the Kumo cloud + Tenkan/Kijun cross + bullish cloud. Chikou span deliberately excluded (look-ahead). A freqtrade staple."},
    "macd_cross": {"label": "MACD Cross (trend-filtered)", "bias": "momentum", "best_for": "trending markets", "source": "freqtrade",
                   "desc": "The canonical freqtrade MACD strategy, gated by EMA200 so crosses are only taken with the higher-timeframe trend."},
    "dmi_adx": {"label": "DMI / ADX Directional", "bias": "trend", "best_for": "strong trends", "source": "freqtrade/jesse",
                "desc": "Wilder's +DI/−DI cross confirmed by ADX≥25 — trades only when a real trend is present, flat in chop."},
    "donchian_turtle": {"label": "Donchian Turtle", "bias": "breakout", "best_for": "trending / breakout", "source": "jesse",
                        "desc": "The classic Turtle channel breakout — long on new 20-bar highs, short on new lows, always-in. No volume filter (vs breakout_volume)."},
    "heikin_trend": {"label": "Heikin-Ashi Trend", "bias": "trend", "best_for": "smooth trends", "source": "freqtrade/jesse",
                     "desc": "Two consecutive Heikin-Ashi candles in-trend, aligned with EMA50>EMA200. Gauntlet: +19% avg, positive 4/4, MC-robust 2/4 — sole ported survivor. ON WATCH: edge is BTC-concentrated + cost-fragile on 3/4 markets. Forward-testing live."},
    "hull_cross": {"label": "Hull MA Cross", "bias": "trend", "best_for": "faster trend turns", "source": "jesse",
                   "desc": "Low-lag Hull Moving Average fast/slow cross with a rising-slow filter — turns faster than an EMA cross while staying smooth."},
    # ── web-researched (Connors short-term mean reversion) ──
    "rsi2_connors": {"label": "Connors RSI(2)", "bias": "range", "best_for": "equities / range-bound FX", "source": "web: Connors",
                     "desc": "Larry Connors' RSI(2) mean reversion: buy washed-out RSI(2)<5 above the 200-SMA, exit above the 5-SMA. Gauntlet KEEP but cost-fragile (1/4) — registered, ON WATCH, not live."},
    "double7_connors": {"label": "Connors Double-7s", "bias": "range", "best_for": "equities / FX mean reversion", "source": "web: Connors",
                        "desc": "Connors' Double-7s: above the 200-SMA, buy a new 7-day low, sell a new 7-day high (mirror below). Gauntlet PROMOTE — +8.2% avg, positive 3/4, MC-robust 3/4, positive on range-bound FX. Diversifies the trend-heavy set. Forward-testing live."},
}

# Strategies ported from freqtrade/jesse — started DISABLED until they survived
# the Monte-Carlo + cost-stress gauntlet (scripts/grade_ported.py). Survivors are
# enabled explicitly, exactly like cooking promotions — nothing auto-deploys.
# Gauntlet outcome: only heikin_trend cleared the KEEP bar (and only on watch);
# the five below were DROP/REVIEW and stay disabled (registered for the marketplace).
PORTED_PENDING: set[str] = {
    "ichimoku_cloud", "macd_cross", "dmi_adx",
    "donchian_turtle", "hull_cross",
}

# Web-researched strategies graded by the gauntlet. double7_connors PROMOTED
# (pos 3/4, MC-robust 3/4, cost-survive 2/4 — and positive on range-bound FX, a
# real diversifier for the trend-heavy set). rsi2_connors stays DISABLED (KEEP but
# cost-fragile 1/4 — registered/on-watch, not live).
WEB_PENDING: set[str] = {"rsi2_connors"}

# Runtime enable/disable (in-memory; StrategyEvolution only ranks/selects enabled ones).
ENABLED: set[str] = set(REGISTRY) - PORTED_PENDING - WEB_PENDING


def is_enabled(name: str) -> bool:
    return name in ENABLED


def set_enabled(name: str, on: bool) -> None:
    if name not in REGISTRY:
        return
    ENABLED.add(name) if on else ENABLED.discard(name)


def build_strategy(name: str, **params) -> Strategy:
    if name not in REGISTRY:
        raise KeyError(f"unknown strategy '{name}'; have {list(REGISTRY)}")
    return REGISTRY[name](**params)


__all__ = [
    "Strategy", "StrategySignal", "REGISTRY", "STRATEGY_INFO", "ENABLED",
    "build_strategy", "is_enabled", "set_enabled",
    "MomentumStrategy", "MeanReversionStrategy", "VwapTrendStrategy",
    "EmaTrendStrategy", "RsiMacdStrategy", "BollingerReversionStrategy", "BreakoutVolumeStrategy",
]
