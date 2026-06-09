"""Evidence for the multi_timeframe + sector_rotation committee-agent review.

The loop rule: backtest their impact on the basket; keep OFF unless they clearly
help. This measures what is honestly measurable:
  1. SectorRotation basket coverage (how many basket symbols it can even vote on)
     + the current live sector ranking.
  2. MultiTimeframe's DAILY directional signal as a strategy through the same
     MC + cost-stress gauntlet used for promotions (the 15m/1h agreement layer is
     not backtestable — yfinance intraday history is ~60 days).
"""
from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")

import pandas as pd

from aifos.agents.sector_rotation import SYMBOL_SECTOR, SectorRotationAgent
from aifos.backtest import cost_stress, monte_carlo, run_backtest
from aifos.config import settings
from aifos.data.providers import get_provider
from aifos.strategies.base import Strategy

BASKET = ["^NSEI", "USDINR=X", "BTC-USD", "RELIANCE.NS"]
CAP = settings.starting_capital


class MtfDailyStrategy(Strategy):
    """MultiTimeframe's daily view as a standalone signal: long when EMA20>EMA50
    and close>EMA50; short when EMA20<EMA50 and close<EMA50; else flat. This is
    the only backtestable part of the agent (the multi-timeframe agreement layer
    needs intraday history yfinance doesn't keep)."""
    name = "mtf_daily"

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        c = df["close"]
        ef = c.ewm(span=20, adjust=False, min_periods=20).mean()
        es = c.ewm(span=50, adjust=False, min_periods=50).mean()
        p = pd.Series(0.0, index=c.index)
        p[(ef > es) & (c > es)] = 1.0
        p[(ef < es) & (c < es)] = -1.0
        return p.fillna(0.0)


def main() -> None:
    provider = get_provider()

    print("=" * 78)
    print("SECTOR ROTATION — basket coverage")
    print("=" * 78)
    covered = [s for s in BASKET if s.upper() in SYMBOL_SECTOR]
    print(f"  basket symbols mapped to a sector: {covered or '— none —'} "
          f"({len(covered)}/{len(BASKET)})")
    print("  -> votes NEUTRAL (confidence 0) on every unmapped symbol\n")
    try:
        scores = SectorRotationAgent(provider=provider)._rank_sectors()
        print("  live NSE sector ranking (20d return):")
        for s in scores:
            print(f"    {s.rank:>2}. {s.sector:8s} {s.return_pct*100:+6.1f}%  ({s.index_symbol})")
    except Exception as e:  # noqa: BLE001
        print(f"  sector ranking unavailable: {e}")

    print("\n" + "=" * 78)
    print("MULTI-TIMEFRAME (daily signal) — gauntlet on the basket")
    print("=" * 78)
    rets, robust, cost_ok = [], 0, 0
    for sym in BASKET:
        try:
            df = provider.history(sym, "1d")
            df.attrs["symbol"] = sym
            res = run_backtest(df, MtfDailyStrategy(), interval="1d", capital=CAP)
            tr = float(res.metrics["total_return"])
            rets.append(tr)
            mc = monte_carlo(res.trades)
            wob = mc.get("return_without_best_trade")
            if tr > 0 and not (wob is not None and wob <= 0 < tr):
                robust += 1
            if cost_stress(df, MtfDailyStrategy(), interval="1d", capital=CAP)["survives_2x_cost"]:
                cost_ok += 1
            print(f"  {sym:12s} return {tr*100:+6.1f}%  trades {len(res.trades):>3}")
        except Exception as e:  # noqa: BLE001
            print(f"  {sym:12s} ERROR {type(e).__name__}")
    if rets:
        avg = sum(rets) / len(rets)
        pos = sum(1 for r in rets if r > 0)
        print(f"\n  avg {avg*100:+.1f}%  positive {pos}/{len(rets)}  "
              f"MC-robust {robust}/{len(rets)}  cost-survive {cost_ok}/{len(rets)}")
        verdict = "CLEARLY HELPS" if (pos >= 3 and robust >= 2 and cost_ok >= 2) else "does NOT clearly help"
        print(f"  daily-signal verdict: {verdict}")


if __name__ == "__main__":
    main()
