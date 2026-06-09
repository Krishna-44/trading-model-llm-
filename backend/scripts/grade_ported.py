"""Grade the freqtrade/jesse-ported strategies through AIFOS's real gauntlet.

Fetches each basket symbol once (real yfinance data), then runs every ported
strategy through backtest -> Monte Carlo -> cost-stress. Prints an honest
scorecard. Nothing is enabled here — this only tells us which survive.
"""
from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")

from aifos.backtest import cost_stress, monte_carlo, run_backtest
from aifos.config import settings
from aifos.data.providers import get_provider
from aifos.strategies.ported import PORTED

BASKET = ["^NSEI", "USDINR=X", "BTC-USD", "RELIANCE.NS"]
CAP = settings.starting_capital


def main() -> None:
    provider = get_provider()
    # Fetch each symbol once, reuse across strategies.
    data: dict[str, object] = {}
    for sym in BASKET:
        try:
            df = provider.history(sym, "1d")
            df.attrs["symbol"] = sym
            data[sym] = df
            print(f"  data {sym:12s} {len(df):>5d} bars  {df.index[0].date()} -> {df.index[-1].date()}")
        except Exception as e:  # noqa: BLE001
            print(f"  data {sym:12s} FAILED: {e}")
    print()

    rows = []
    for name, cls in PORTED.items():
        rets, robust, cost_ok, trades_tot = [], 0, 0, 0
        per_market = []
        for sym, df in data.items():
            try:
                res = run_backtest(df, cls(), interval="1d", capital=CAP)
                tr = float(res.metrics["total_return"])
                rets.append(tr)
                trades_tot += len(res.trades)
                mc = monte_carlo(res.trades)
                wob = mc.get("return_without_best_trade")
                mc_robust = tr > 0 and not (wob is not None and wob <= 0 < tr)
                if mc_robust:
                    robust += 1
                cs = cost_stress(df, cls(), interval="1d", capital=CAP)
                if cs["survives_2x_cost"]:
                    cost_ok += 1
                per_market.append(f"{sym.split('=')[0].split('.')[0]}={tr*100:+.0f}%")
            except Exception as e:  # noqa: BLE001
                per_market.append(f"{sym}=ERR({type(e).__name__})")
        if not rets:
            rows.append((name, 0.0, 0, 0, 0, 0, "DROP", "no data"))
            continue
        avg = sum(rets) / len(rets)
        positive = sum(1 for r in rets if r > 0)
        # Promotion bar (stricter than cooking KEEP): broad + MC-robust + cost-robust.
        if positive >= 3 and robust >= 2 and cost_ok >= 2 and avg > 0:
            verdict = "PROMOTE"
        elif robust >= 2 and avg > 0:
            verdict = "KEEP"
        elif robust >= 1 and avg > -0.05:
            verdict = "REVIEW"
        else:
            verdict = "DROP"
        rows.append((name, avg, positive, robust, cost_ok, trades_tot, verdict,
                     " ".join(per_market)))

    print("=" * 100)
    print(f"{'strategy':18s} {'avg':>7s} {'pos':>4s} {'mc':>4s} {'cost':>5s} {'trades':>7s}  {'verdict':8s} detail")
    print("-" * 100)
    for name, avg, pos, rob, cost_ok, ntr, verdict, detail in rows:
        print(f"{name:18s} {avg*100:>6.1f}% {pos:>3d}/4 {rob:>3d}/4 {cost_ok:>4d}/4 {ntr:>7d}  {verdict:8s} {detail}")
    print("=" * 100)
    promote = [r[0] for r in rows if r[6] == "PROMOTE"]
    keep = [r[0] for r in rows if r[6] == "KEEP"]
    print(f"\nPROMOTE (enable + forward-test): {promote or '— none —'}")
    print(f"KEEP (registry, watch):          {keep or '— none —'}")


if __name__ == "__main__":
    main()
