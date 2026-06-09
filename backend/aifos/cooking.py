"""Strategy cooking — continuous discovery loop.

Background research: each round picks one CANDIDATE (a parameter variant of an
existing strategy, or a hybrid combining two), backtests it on a real multi-market
basket, runs Monte Carlo for robustness, and persists the result with an honest
verdict (KEEP / REVIEW / DROP).

This is *real* research — not a fake animation. It will rarely produce a strategy
that genuinely beats the existing set; that's the honest nature of strategy
discovery. The leaderboard surfaces what's actually working across cooking rounds.

Promotion to the live registry is a SEPARATE human-approval step (the UI lets you
inspect, then enable). We never auto-deploy untested edges into the marathon.
"""
from __future__ import annotations

import logging

import pandas as pd

from .backtest import monte_carlo, run_backtest
from .config import settings
from .indicators import adx, ema, macd, rsi, supertrend, vwap
from .strategies.base import Strategy
from .strategies.web_sourced import ConnorsDouble7Strategy, ConnorsRsi2Strategy

logger = logging.getLogger("aifos.cooking")

BASKET = ["^NSEI", "USDINR=X", "BTC-USD", "RELIANCE.NS"]


# ── parameterizable strategy variants ──────────────────────────────────────
def _pos(index, long, short) -> pd.Series:
    p = pd.Series(0.0, index=index)
    p[long] = 1.0
    p[short] = -1.0
    return p.fillna(0.0)


class EmaTrendVariant(Strategy):
    name = "ema_trend_v"

    def __init__(self, short: int = 20, mid: int = 50, long: int = 200) -> None:
        self.short, self.mid, self.long = short, mid, long

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        c = df["close"]
        a, b, d = ema(c, self.short), ema(c, self.mid), ema(c, self.long)
        return _pos(c.index, (a > b) & (b > d), (a < b) & (b < d))


class RsiMacdVariant(Strategy):
    name = "rsi_macd_v"

    def __init__(self, long_thresh: int = 52, short_thresh: int = 48) -> None:
        self.long_thresh, self.short_thresh = long_thresh, short_thresh

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        c = df["close"]
        r = rsi(c)
        hist = macd(c)["hist"]
        return _pos(c.index, (r > self.long_thresh) & (hist > 0),
                    (r < self.short_thresh) & (hist < 0))


class SupertrendVariant(Strategy):
    name = "supertrend_v"

    def __init__(self, window: int = 10, mult: float = 3.0, adx_floor: int = 20) -> None:
        self.window, self.mult, self.adx_floor = window, mult, adx_floor

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        c = df["close"]
        st = supertrend(df["high"], df["low"], c, window=self.window, mult=self.mult)
        a = adx(df["high"], df["low"], c)["adx"]
        ok = a >= self.adx_floor
        return _pos(c.index, (st["direction"] > 0) & ok, (st["direction"] < 0) & ok)


class HybridEmaRsiStrategy(Strategy):
    """Hybrid: ema_trend AND rsi_macd must AGREE on direction — fewer but
    higher-conviction signals. Honest ensemble (no curve-fitting)."""
    name = "hybrid_ema_rsi"

    def __init__(self, short: int = 20, mid: int = 50, long: int = 200,
                 rsi_long: int = 52, rsi_short: int = 48) -> None:
        self.short, self.mid, self.long = short, mid, long
        self.rsi_long, self.rsi_short = rsi_long, rsi_short

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        c = df["close"]
        a, b, d = ema(c, self.short), ema(c, self.mid), ema(c, self.long)
        r = rsi(c)
        hist = macd(c)["hist"]
        ema_long = (a > b) & (b > d)
        ema_short = (a < b) & (b < d)
        rsi_long = (r > self.rsi_long) & (hist > 0)
        rsi_short = (r < self.rsi_short) & (hist < 0)
        return _pos(c.index, ema_long & rsi_long, ema_short & rsi_short)


class VwapEmaHybridStrategy(Strategy):
    """Hybrid: VWAP institutional bias AND EMA trend — only trade trends that
    also have institutional confirmation."""
    name = "hybrid_vwap_ema"

    def __init__(self, vwap_window: int = 20, ema_window: int = 50) -> None:
        self.vwap_window, self.ema_window = vwap_window, ema_window

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        c = df["close"]
        vw = vwap(df["high"], df["low"], c, df["volume"], self.vwap_window)
        e = ema(c, self.ema_window)
        return _pos(c.index, (c > vw) & (c > e) & (e > e.shift(5)),
                    (c < vw) & (c < e) & (e < e.shift(5)))


# ── candidate queue ────────────────────────────────────────────────────────
# Each entry: (variant_id, base_name, build_fn). variant_id encodes the params so
# cooking persists per-variant. The cooker round-robins through this list.
CANDIDATES: list[tuple[str, str, type, dict]] = [
    # EMA trend variants — try faster + slower windows
    ("ema_trend(10,30,100)",  "ema_trend",  EmaTrendVariant,  {"short": 10, "mid": 30, "long": 100}),
    ("ema_trend(20,50,200)",  "ema_trend",  EmaTrendVariant,  {"short": 20, "mid": 50, "long": 200}),
    ("ema_trend(8,21,55)",    "ema_trend",  EmaTrendVariant,  {"short": 8, "mid": 21, "long": 55}),
    ("ema_trend(13,34,89)",   "ema_trend",  EmaTrendVariant,  {"short": 13, "mid": 34, "long": 89}),
    # RSI+MACD threshold sweeps
    ("rsi_macd(55,45)",       "rsi_macd",   RsiMacdVariant,   {"long_thresh": 55, "short_thresh": 45}),
    ("rsi_macd(60,40)",       "rsi_macd",   RsiMacdVariant,   {"long_thresh": 60, "short_thresh": 40}),
    ("rsi_macd(50,50)",       "rsi_macd",   RsiMacdVariant,   {"long_thresh": 50, "short_thresh": 50}),
    # Supertrend variants
    ("supertrend(10,3,20)",   "supertrend", SupertrendVariant, {"window": 10, "mult": 3.0, "adx_floor": 20}),
    ("supertrend(14,2,25)",   "supertrend", SupertrendVariant, {"window": 14, "mult": 2.0, "adx_floor": 25}),
    ("supertrend(7,4,15)",    "supertrend", SupertrendVariant, {"window": 7, "mult": 4.0, "adx_floor": 15}),
    # Hybrids (ensembles)
    ("hybrid_ema_rsi(default)", "hybrid_ema_rsi", HybridEmaRsiStrategy, {}),
    ("hybrid_ema_rsi(fast)",  "hybrid_ema_rsi", HybridEmaRsiStrategy,
                                {"short": 10, "mid": 30, "long": 100, "rsi_long": 55, "rsi_short": 45}),
    ("hybrid_vwap_ema(20,50)", "hybrid_vwap_ema", VwapEmaHybridStrategy, {"vwap_window": 20, "ema_window": 50}),
    ("hybrid_vwap_ema(14,30)", "hybrid_vwap_ema", VwapEmaHybridStrategy, {"vwap_window": 14, "ema_window": 30}),
    # Web-researched Connors mean-reversion — tune thresholds/window in the loop
    ("rsi2_connors(5,95)",     "rsi2_connors",    ConnorsRsi2Strategy,    {"low": 5, "high": 95}),
    ("rsi2_connors(10,90)",    "rsi2_connors",    ConnorsRsi2Strategy,    {"low": 10, "high": 90}),
    ("rsi2_connors(3,97)",     "rsi2_connors",    ConnorsRsi2Strategy,    {"low": 3, "high": 97}),
    ("double7_connors(7)",     "double7_connors", ConnorsDouble7Strategy, {"window": 7}),
    ("double7_connors(5)",     "double7_connors", ConnorsDouble7Strategy, {"window": 5}),
    ("double7_connors(10)",    "double7_connors", ConnorsDouble7Strategy, {"window": 10}),
]


# ── the cooker ─────────────────────────────────────────────────────────────
def cook_one(provider, candidate: tuple) -> dict:
    """Backtest a single candidate across the basket, run MC, return verdict."""
    variant_id, base, cls, params = candidate
    rets, robust_count = [], 0
    for sym in BASKET:
        try:
            df = provider.history(sym, "1d")
            df.attrs["symbol"] = sym
            res = run_backtest(df, cls(**params), interval="1d",
                               capital=settings.starting_capital)
            tr = float(res.metrics["total_return"])
            rets.append(tr)
            mc = monte_carlo(res.trades)
            wob = mc.get("return_without_best_trade")
            # robust = profitable AND edge survives losing the single best trade
            if tr > 0 and not (wob is not None and wob <= 0 < tr):
                robust_count += 1
        except Exception:  # noqa: BLE001 - one symbol's failure can't kill the round
            continue
    if not rets:
        return {"variant_id": variant_id, "base": base, "params": params,
                "avg_return": 0.0, "markets_positive": 0, "mc_robust_count": 0,
                "markets_tested": 0, "verdict": "DROP", "note": "no data"}
    avg = sum(rets) / len(rets)
    positive = sum(1 for r in rets if r > 0)
    if robust_count >= 2 and avg > 0:
        verdict, note = "KEEP", "MC-robust on 2+ markets and profitable on average"
    elif robust_count >= 1 and avg > -0.05:
        verdict, note = "REVIEW", "single-market robustness — promising but unproven"
    else:
        verdict = "DROP"
        note = (f"avg {avg*100:+.1f}% across {len(rets)} markets · "
                f"{robust_count} MC-robust — no edge")
    return {"variant_id": variant_id, "base": base, "params": params,
            "avg_return": round(avg, 4), "markets_positive": positive,
            "mc_robust_count": robust_count, "markets_tested": len(rets),
            "verdict": verdict, "note": note}


def pick_next_candidate(recent_variant_ids: list[str]) -> tuple | None:
    """Round-robin: pick the candidate cooked LEAST recently. Fairness > greed —
    we don't want to keep re-testing the same variant while others sit unbenched."""
    if not CANDIDATES:
        return None
    seen_positions = {vid: i for i, vid in enumerate(recent_variant_ids)}
    # Sort candidates by their most-recent index (high = unseen, low = recent)
    sorted_cands = sorted(CANDIDATES,
                          key=lambda c: seen_positions.get(c[0], 1_000_000),
                          reverse=True)
    return sorted_cands[0]
