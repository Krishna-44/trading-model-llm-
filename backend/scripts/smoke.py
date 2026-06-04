"""End-to-end smoke test of the AIFOS spine. Run: python scripts/smoke.py
Exercises data -> committee -> risk -> paper execution -> backtest -> storage.
Network-independent: data layer falls back to a synthetic series if offline."""
from __future__ import annotations

import sys

from aifos.backtest import run_backtest, walk_forward
from aifos.config import settings
from aifos.kernel import get_kernel
from aifos.persistence.db import init_db
from aifos.strategies import build_strategy


def main() -> int:
    init_db()
    k = get_kernel()
    sym = settings.default_symbol

    print(f"\n=== AIFOS smoke | broker={k.broker.name} live={settings.live_trading_enabled} ===")

    decision, ctx = k.analyze(sym, "1d")
    print(f"\n[analyze {sym}] source={decision.source} price={ctx.price:.2f} atr={ctx.atr:.2f}")
    print(f"  -> {decision.action} ({decision.side}) confidence={decision.confidence:.0%}")
    print(f"  reasoning: {decision.reasoning}")
    print(f"  agents: {len(decision.opinions)} | llm_summary: {decision.llm_summary[:90]}...")
    for o in decision.opinions:
        flag = " VETO" if o.veto else ""
        print(f"    - {o.agent:24s} {o.stance:8s} conf={o.confidence:.2f}{flag}")

    print("\n[backtest momentum]")
    df = k.provider.history(sym, "1d"); df.attrs["symbol"] = sym
    res = run_backtest(df, build_strategy("momentum"), interval="1d",
                       capital=settings.starting_capital)
    m = res.metrics
    print(f"  return={m['total_return']:.1%} sharpe={m['sharpe']} maxDD={m['max_drawdown']:.1%} "
          f"trades={m['num_trades']} winrate={m['win_rate']:.0%}")
    wf = walk_forward(df, build_strategy("momentum"), interval="1d")
    print(f"  walk-forward OOS sharpe={wf['oos'].get('sharpe')} folds={len(wf['folds'])}")

    print("\n[paper trade cycle on BTC-USD]")
    d2, fill = k.tick("BTC-USD", "1d", execute=True)
    print(f"  decision={d2.action} executed={d2.executed} fill={'yes' if fill else 'none'}")

    pf = k.portfolio()
    print(f"\n[portfolio] equity={pf['account']['equity']:.2f} cash={pf['account']['cash']:.2f} "
          f"positions={pf['open_positions']} mode={pf['mode']}")
    print(f"[risk] {k.risk_snapshot()['limits']}")
    print(f"[memory] situations stored: {k.memory.stats()['count']}")
    print("\n=== SMOKE OK ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
