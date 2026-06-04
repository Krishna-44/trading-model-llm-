"""Institutional performance analytics — computed honestly from real data.

Two views:
  * ``portfolio_analytics`` — the LIVE/paper account: realized P&L, win rate,
    profit factor, expectancy, Sharpe/Sortino/max-drawdown from the equity curve,
    and daily/weekly/monthly P&L. Sparse until trades close — reported as zeros,
    never invented.
  * ``strategy_comparison`` — backtested metrics per strategy on a symbol, so the
    "compare strategies" view is populated immediately and verifiably.

Transparent + auditable by construction: every number traces to stored trades /
equity points or a reproducible backtest. Nothing here implies guaranteed profit.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from .backtest import run_backtest
from .config import settings
from .data.models import classify_asset
from .strategies import REGISTRY, build_strategy


def _safe(a: float, b: float) -> float:
    return float(a / b) if b else 0.0


def _equity_stats(curve: list[dict]) -> dict:
    eq = [float(p["equity"]) for p in curve]
    if len(eq) < 2:
        return {"sharpe": 0.0, "sortino": 0.0, "max_drawdown": 0.0, "total_return": 0.0,
                "points": len(eq), "current_equity": eq[-1] if eq else settings.starting_capital}
    arr = np.array(eq)
    rets = arr[1:] / arr[:-1] - 1
    ann = 252
    sharpe = _safe(rets.mean() * ann, rets.std(ddof=0) * np.sqrt(ann))
    dn = rets[rets < 0]
    sortino = _safe(rets.mean() * ann, dn.std(ddof=0) * np.sqrt(ann)) if len(dn) else 0.0
    roll_max = np.maximum.accumulate(arr)
    max_dd = float((arr / roll_max - 1).min())
    return {"sharpe": round(sharpe, 3), "sortino": round(sortino, 3),
            "max_drawdown": round(max_dd, 4), "total_return": round(_safe(arr[-1], arr[0]) - 1, 4),
            "points": len(eq), "current_equity": round(float(arr[-1]), 2)}


def _window_pnl(curve: list[dict], days: int) -> float:
    if not curve:
        return 0.0
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    pts = []
    for p in curve:
        if not p.get("ts"):
            continue
        try:
            t = datetime.fromisoformat(p["ts"]).replace(tzinfo=None)
        except ValueError:
            continue
        pts.append((t, float(p["equity"])))
    if not pts:
        return 0.0
    latest = pts[-1][1]
    prior = [e for (t, e) in pts if t <= cutoff]
    base = prior[-1] if prior else pts[0][1]
    return round(latest - base, 2)


def _trade_stats(trades: list[dict]) -> dict:
    closed = [t for t in trades if t.get("realized_pnl", 0.0) != 0.0]
    wins = [t for t in closed if t["realized_pnl"] > 0]
    losses = [t for t in closed if t["realized_pnl"] <= 0]
    gross_win = sum(t["realized_pnl"] for t in wins)
    gross_loss = abs(sum(t["realized_pnl"] for t in losses))
    avg_w, avg_l = _safe(gross_win, len(wins)), _safe(gross_loss, len(losses))
    win_rate = _safe(len(wins), len(closed))
    expectancy = win_rate * avg_w - (1 - win_rate) * avg_l
    return {"closed_trades": len(closed),
            "realized_pnl": round(sum(t["realized_pnl"] for t in closed), 2),
            "win_rate": round(win_rate, 3), "profit_factor": round(_safe(gross_win, gross_loss), 3),
            "avg_win": round(avg_w, 2), "avg_loss": round(avg_l, 2),
            "payoff_ratio": round(_safe(avg_w, avg_l), 3), "expectancy": round(expectancy, 2)}


def portfolio_analytics(repo) -> dict:
    curve = repo.equity_curve(5000)
    trades = repo.recent_trades(5000)
    ts = _trade_stats(trades)
    return {
        **_equity_stats(curve), **ts,
        "daily_pnl": _window_pnl(curve, 1),
        "weekly_pnl": _window_pnl(curve, 7),
        "monthly_pnl": _window_pnl(curve, 30),
        "note": ("metrics populate as paper/live trades close — shown as zero, never invented"
                 if ts["closed_trades"] == 0 else ""),
    }


def track_record(repo, account, starting_capital: float) -> dict:
    """Single honest 'is it working on paper?' report, since inception.

    Every field traces to stored decisions/trades/equity points or the live
    mark-to-market account. Sparse fields are zero, never invented.
    """
    curve = repo.equity_curve(5000)
    trades = repo.recent_trades(5000)
    eq = _equity_stats(curve)
    ts = _trade_stats(trades)

    inception = repo.inception_ts()
    days = 0.0
    if inception:
        try:
            start = datetime.fromisoformat(inception).replace(tzinfo=None)
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            days = round((now - start).total_seconds() / 86400.0, 2)
        except ValueError:
            days = 0.0

    equity_now = round(float(account.equity), 2)
    realized = round(float(account.realized_pnl), 2)
    unrealized = round(equity_now - starting_capital - realized, 2)

    pts = [{"ts": p.get("ts"), "equity": round(float(p["equity"]), 2)} for p in curve]
    if len(pts) > 240:                       # keep the curve light for the UI
        step = len(pts) // 240 + 1
        pts = pts[::step] + [pts[-1]]

    return {
        "inception": inception,
        "days_running": days,
        "starting_capital": round(float(starting_capital), 2),
        "current_equity": equity_now,
        "total_return": round(_safe(equity_now - starting_capital, starting_capital), 4),
        "realized_pnl": realized,
        "unrealized_pnl": unrealized,
        "daily_pnl": _window_pnl(curve, 1),
        "weekly_pnl": _window_pnl(curve, 7),
        "monthly_pnl": _window_pnl(curve, 30),
        "decisions": repo.count_decisions(),
        "executed": repo.count_executed(),
        "execution_rate": round(_safe(repo.count_executed(), repo.count_decisions()), 3),
        "closed_trades": ts["closed_trades"],
        "win_rate": ts["win_rate"],
        "profit_factor": ts["profit_factor"],
        "expectancy": ts["expectancy"],
        "sharpe": eq["sharpe"],
        "sortino": eq["sortino"],
        "max_drawdown": eq["max_drawdown"],
        "equity_points": eq["points"],
        "curve": pts,
        "note": ("Forward paper test — metrics populate as cycles run and trades close. "
                 "Zeros are honest, not failures. Past results never guarantee future ones."),
    }


def strategy_comparison(provider, symbol: str, interval: str = "1d") -> list[dict]:
    df = provider.history(symbol, interval)
    df.attrs["symbol"] = symbol
    out: list[dict] = []
    for name in REGISTRY:
        try:
            m = run_backtest(df, build_strategy(name), interval=interval,
                             capital=settings.starting_capital).metrics
            out.append({"strategy": name, "total_return": m["total_return"], "sharpe": m["sharpe"],
                        "sortino": m["sortino"], "max_drawdown": m["max_drawdown"],
                        "win_rate": m["win_rate"], "profit_factor": m["profit_factor"],
                        "num_trades": m["num_trades"]})
        except Exception as exc:  # noqa: BLE001
            out.append({"strategy": name, "error": str(exc)})
    return out


def correlation_matrix(provider, symbols: list[str], interval: str = "1d",
                       lookback: int = 120) -> dict:
    """Pairwise return correlation across the universe (real returns)."""
    rets: dict[str, pd.Series] = {}
    for s in symbols:
        try:
            r = provider.history(s, interval)["close"].pct_change().dropna().tail(lookback)
            if len(r) > 20:
                rets[s] = r.reset_index(drop=True)
        except Exception:  # noqa: BLE001
            continue
    if len(rets) < 2:
        return {"symbols": list(rets), "matrix": []}
    frame = pd.DataFrame(rets).dropna()
    corr = frame.corr()
    syms = list(corr.columns)
    matrix = [[round(float(corr.iloc[i, j]), 2) for j in range(len(syms))]
              for i in range(len(syms))]
    return {"symbols": syms, "matrix": matrix}


def market_heatmap(provider, symbols: list[str], interval: str = "1d") -> list[dict]:
    """Last price + 1-bar % change per symbol, for the universe heatmap."""
    out: list[dict] = []
    for s in symbols:
        try:
            c = provider.history(s, interval)["close"]
            price = float(c.iloc[-1])
            prev = float(c.iloc[-2]) if len(c) > 1 else price
            out.append({"symbol": s, "asset_class": classify_asset(s).value,
                        "price": round(price, 2),
                        "change_pct": round(price / prev - 1, 4) if prev else 0.0})
        except Exception as exc:  # noqa: BLE001
            out.append({"symbol": s, "error": str(exc)})
    return out
