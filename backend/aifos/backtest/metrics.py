"""Performance metrics. Honest about small samples — Sharpe/Sortino are NaN-safe
and return 0.0 rather than exploding on near-zero volatility."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _safe_div(a: float, b: float) -> float:
    return float(a / b) if b not in (0, 0.0) and not np.isnan(b) else 0.0


def compute_metrics(
    returns: pd.Series, equity: pd.Series, trades: list[dict],
    periods_per_year: int = 252,
) -> dict:
    r = returns.dropna()
    n = len(r)
    if n == 0 or equity.empty:
        return {k: 0.0 for k in (
            "total_return", "cagr", "ann_return", "ann_vol", "sharpe", "sortino",
            "max_drawdown", "win_rate", "profit_factor", "exposure", "num_trades",
        )}

    total_return = _safe_div(equity.iloc[-1], equity.iloc[0]) - 1
    ann_return = float(r.mean() * periods_per_year)
    ann_vol = float(r.std(ddof=0) * np.sqrt(periods_per_year))
    downside = r[r < 0]
    downside_vol = float(downside.std(ddof=0) * np.sqrt(periods_per_year)) if len(downside) else 0.0
    cagr = (_safe_div(equity.iloc[-1], equity.iloc[0])) ** (periods_per_year / n) - 1 if equity.iloc[0] > 0 else 0.0

    roll_max = equity.cummax()
    drawdown = equity / roll_max - 1
    max_dd = float(drawdown.min())

    wins = [t for t in trades if t["pnl_pct"] > 0]
    losses = [t for t in trades if t["pnl_pct"] <= 0]
    gross_win = sum(t["pnl_pct"] for t in wins)
    gross_loss = abs(sum(t["pnl_pct"] for t in losses))

    return {
        "total_return": round(total_return, 4),
        "cagr": round(float(cagr), 4),
        "ann_return": round(ann_return, 4),
        "ann_vol": round(ann_vol, 4),
        "sharpe": round(_safe_div(ann_return, ann_vol), 3),
        "sortino": round(_safe_div(ann_return, downside_vol), 3),
        "max_drawdown": round(max_dd, 4),
        "win_rate": round(_safe_div(len(wins), len(trades)), 3) if trades else 0.0,
        "profit_factor": round(_safe_div(gross_win, gross_loss), 3),
        "exposure": round(float((returns != 0).mean()), 3),
        "num_trades": len(trades),
    }
