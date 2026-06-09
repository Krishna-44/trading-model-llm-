"""Vectorized backtester.

Guarantees:
  * No look-ahead: positions are lagged one bar before being applied to returns.
  * Costs are real: commission + slippage charged on every unit of turnover.
  * Walk-forward: out-of-sample evaluation across expanding folds, so reported
    edge is not in-sample curve fitting.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..strategies.base import Strategy
from .metrics import compute_metrics

_PPY = {"1d": 252, "1wk": 52, "1mo": 12, "1h": 252 * 7, "60m": 252 * 7}


@dataclass
class BacktestResult:
    symbol: str
    strategy: str
    equity_curve: pd.Series
    returns: pd.Series
    positions: pd.Series
    trades: list[dict]
    metrics: dict
    source: str = "unknown"

    def to_payload(self) -> dict:
        eq = self.equity_curve
        return {
            "symbol": self.symbol,
            "strategy": self.strategy,
            "metrics": self.metrics,
            "source": self.source,
            "equity_curve": [
                {"ts": ts.isoformat(), "equity": round(float(v), 2)}
                for ts, v in eq.items()
            ],
            "trades": self.trades[-50:],
        }


def _extract_trades(positions: pd.Series, close: pd.Series) -> list[dict]:
    """Segment contiguous nonzero positions into discrete round-trip trades."""
    trades: list[dict] = []
    pos = positions.values
    idx = positions.index
    i, n = 0, len(pos)
    while i < n:
        if pos[i] == 0:
            i += 1
            continue
        side = np.sign(pos[i])
        start = i
        while i < n and np.sign(pos[i]) == side:
            i += 1
        end = min(i, n - 1)
        entry_px, exit_px = float(close.iloc[start]), float(close.iloc[end])
        pnl_pct = side * (exit_px / entry_px - 1) if entry_px else 0.0
        trades.append({
            "entry_ts": idx[start].isoformat(),
            "exit_ts": idx[end].isoformat(),
            "side": "long" if side > 0 else "short",
            "entry": round(entry_px, 4),
            "exit": round(exit_px, 4),
            "bars": int(end - start),
            "pnl_pct": round(float(pnl_pct), 4),
        })
    return trades


def run_backtest(
    df: pd.DataFrame, strategy: Strategy, *, interval: str = "1d",
    capital: float = 1_000_000.0, cost_bps: float = 5.0, slippage_bps: float = 2.0,
) -> BacktestResult:
    signals = strategy.generate_signals(df).reindex(df.index).fillna(0.0)
    pos = signals.shift(1).fillna(0.0)  # enter NEXT bar -> no look-ahead
    asset_ret = df["close"].pct_change().fillna(0.0)
    turnover = pos.diff().abs().fillna(pos.abs())
    cost = turnover * (cost_bps + slippage_bps) / 1e4
    strat_ret = pos * asset_ret - cost
    equity = (1 + strat_ret).cumprod() * capital
    trades = _extract_trades(pos, df["close"])
    metrics = compute_metrics(strat_ret, equity, trades, _PPY.get(interval, 252))
    return BacktestResult(
        symbol=getattr(df, "attrs", {}).get("symbol", "?"),
        strategy=strategy.name,
        equity_curve=equity, returns=strat_ret, positions=pos,
        trades=trades, metrics=metrics,
        source=df.attrs.get("source", "unknown"),
    )


def walk_forward(
    df: pd.DataFrame, strategy: Strategy, *, interval: str = "1d",
    n_splits: int = 4, capital: float = 1_000_000.0,
) -> dict:
    """Expanding-window out-of-sample evaluation.

    Fold k trains on [0, t_k) and is *scored* on [t_k, t_{k+1}). Since these
    strategies are rule-based (no fitting), this mainly proves robustness across
    regimes; the same harness supports parameter-fit strategies later.
    """
    n = len(df)
    if n < n_splits * 30:
        res = run_backtest(df, strategy, interval=interval, capital=capital)
        return {"folds": [], "oos": res.metrics, "note": "series too short for folds"}

    bounds = np.linspace(int(n * 0.4), n, n_splits + 1).astype(int)
    fold_metrics, oos_returns = [], []
    for k in range(n_splits):
        test = df.iloc[bounds[k]:bounds[k + 1]]
        if len(test) < 20:
            continue
        r = run_backtest(test, strategy, interval=interval, capital=capital)
        fold_metrics.append({"window": [test.index[0].isoformat(), test.index[-1].isoformat()],
                             **r.metrics})
        oos_returns.append(r.returns)

    if not oos_returns:
        return {"folds": [], "oos": {}, "note": "no valid folds"}
    combined = pd.concat(oos_returns)
    eq = (1 + combined).cumprod() * capital
    oos = compute_metrics(combined, eq, [], _PPY.get(interval, 252))
    return {"folds": fold_metrics, "oos": oos,
            "note": "out-of-sample aggregate across expanding folds"}


def cost_stress(df: pd.DataFrame, strategy: Strategy, *, interval: str = "1d",
                capital: float = 1_000_000.0, base_cost_bps: float = 5.0,
                base_slip_bps: float = 2.0) -> dict:
    """Re-run the backtest at escalating transaction costs (1× → 3× commission +
    slippage) to test whether the edge survives realistic-worse friction. An edge
    that is only profitable at near-frictionless costs is NOT real — spreads widen,
    fills slip, and a strategy that can't pay for its own turnover should be cut.

    Returns the net return at each cost multiple plus ``cost_fragile`` = profitable
    at 1× but underwater by 2×.
    """
    levels = []
    for m in (1.0, 1.5, 2.0, 3.0):
        try:
            res = run_backtest(df, strategy, interval=interval, capital=capital,
                               cost_bps=base_cost_bps * m, slippage_bps=base_slip_bps * m)
            levels.append({"mult": m, "total_return": round(float(res.metrics["total_return"]), 4)})
        except Exception:  # noqa: BLE001
            levels.append({"mult": m, "total_return": 0.0})
    base = levels[0]["total_return"]
    r2x = next((x["total_return"] for x in levels if x["mult"] == 2.0), 0.0)
    return {
        "levels": levels,
        "base_return": base,
        "return_at_2x_cost": r2x,
        "survives_2x_cost": bool(r2x > 0),
        "cost_fragile": bool(base > 0 and r2x <= 0),
        "note": "net return vs escalating slippage+commission; fragile = positive at 1× but gone by 2×",
    }


def monte_carlo(trades: list[dict], *, n_sims: int = 2000, seed: int = 7) -> dict:
    """Bootstrap the per-trade returns to estimate the DISTRIBUTION of outcomes.

    A genuine edge survives reshuffling; a fragile one (too few trades, or one
    dominant winner) shows a wide spread, a weak P(profit), or collapses when its
    single best trade is removed. Honest by construction: it cannot invent losses
    that never happened, so instead of reporting a falsely reassuring number it
    flags small / all-winning samples in ``verdict`` and sets ``reliable=False``.
    """
    rets = np.array([float(t.get("pnl_pct", 0.0)) for t in trades], dtype=float)
    n = int(rets.size)
    wins, losses = int((rets > 0).sum()), int((rets < 0).sum())
    out: dict = {"n_trades": n, "wins": wins, "losses": losses, "sims": n_sims}
    if n < 2:
        return {**out, "reliable": False, "verdict": "too few trades for Monte Carlo"}

    rng = np.random.default_rng(seed)
    finals = np.empty(n_sims)
    mdds = np.empty(n_sims)
    for s in range(n_sims):
        seq = rng.choice(rets, size=n, replace=True)          # resample a path
        eq = np.concatenate([[1.0], np.cumprod(1.0 + seq)])
        finals[s] = eq[-1] - 1.0
        peak = np.maximum.accumulate(eq)
        mdds[s] = float(((eq - peak) / peak).min())

    real_total = float(np.prod(1.0 + rets) - 1.0)
    without_best = float(np.prod(1.0 + np.delete(rets, int(np.argmax(rets)))) - 1.0)
    gross_wins = float(rets[rets > 0].sum())
    best_share = float(rets.max() / gross_wins) if gross_wins > 0 and rets.max() > 0 else 0.0
    reliable = n >= 30 and losses >= 3

    flags: list[str] = []
    if n < 30:
        flags.append(f"small sample (n={n}) — not statistically reliable")
    if losses == 0:
        flags.append("no losing trades in the sample — bootstrap can't model the downside")
    if real_total > 0 and without_best <= 0:
        flags.append("edge disappears without the single best trade — one-trade-dependent")
    elif best_share >= 0.5:
        flags.append(f"one trade is {best_share:.0%} of gross winnings — concentrated")

    return {**out,
            "reliable": bool(reliable),
            "basis": "gross per-trade returns (excludes per-bar holding cost) — a "
                     "robustness/fragility signal, not a net-return forecast",
            "real_total_return": round(real_total, 4),
            "p_profit": round(float((finals > 0).mean()), 3),
            "median_return": round(float(np.median(finals)), 4),
            "p05_return": round(float(np.percentile(finals, 5)), 4),
            "p95_return": round(float(np.percentile(finals, 95)), 4),
            "median_max_drawdown": round(float(np.median(mdds)), 4),
            "worst_max_drawdown": round(float(mdds.min()), 4),
            "return_without_best_trade": round(without_best, 4),
            "best_trade_share_of_gross_wins": round(best_share, 3),
            "verdict": "; ".join(flags) if flags else "broad-based — survives reshuffling"}
