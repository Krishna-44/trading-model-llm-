from .base import Strategy, StrategySignal
from .library import (
    AtrMomentumStrategy,
    BollingerReversionStrategy,
    BreakoutVolumeStrategy,
    EmaTrendFastStrategy,
    EmaTrendStrategy,
    KeltnerSqueezeStrategy,
    RsiMacdStrategy,
    SupertrendFastStrategy,
    SupertrendStrategy,
    VwapTrendStrategy,
)
from .mean_reversion import MeanReversionStrategy
from .momentum import MomentumStrategy

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
}

# Runtime enable/disable (in-memory; StrategyEvolution only ranks/selects enabled ones).
ENABLED: set[str] = set(REGISTRY)


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
