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
