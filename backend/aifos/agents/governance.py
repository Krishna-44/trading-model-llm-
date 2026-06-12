"""Governance agents: they rarely vote a direction — they protect capital.

  * StrategyEvolution picks the best-performing strategy for this symbol (the
    seed of self-optimization) and writes it into the context.
  * RiskManager / PortfolioOptimizer damp or veto on portfolio-level danger.
  * Compliance enforces hard legal/structural rules (incl. the FEMA guard).
  * Executor turns an APPROVED, sized decision into a broker order.
"""
from __future__ import annotations

from ..backtest import cost_stress, monte_carlo, run_backtest, walk_forward
from ..config import settings
from ..data.models import AssetClass, is_offshore_forex
from ..execution.base import BrokerAdapter, Fill, Order, OrderSide
from ..strategies import REGISTRY, build_strategy, is_enabled
from .base import Agent, AgentOpinion, MarketContext


# OOS selection scores depend only on history up to the last closed bar, so they are
# memoized per (symbol, interval) and recomputed only when a new bar arrives — otherwise
# every 300s cycle would re-run 15 walk-forwards on the identical daily bar. One entry
# per (symbol, interval); bounded by the universe size.
_SEL_CACHE: dict[tuple[str, str], tuple[str, dict[str, float]]] = {}


class StrategyEvolutionAgent(Agent):
    name = "Strategy Evolution"
    weight = 0.0  # advisory: selects the tool, does not vote direction

    def analyze(self, ctx: MarketContext) -> AgentOpinion:
        interval = ctx.extra.get("interval", "1d")
        scores = self._oos_scores(ctx, interval)
        # fallback is the real-edge default (BTC OOS leader), never the in-sample 'momentum'
        best = max(scores, key=scores.get) if scores else "ema_trend_fib"
        ctx.extra["strategy_name"] = best
        return AgentOpinion(
            self.name, "neutral", 0.5, self.weight,
            f"Selected '{best}' for {ctx.symbol} (best OOS-robust backtest). "
            f"Scores: {{{', '.join(f'{k}:{v:.2f}' for k, v in scores.items())}}}",
            {"selected": best, "scores": {k: round(v, 3) for k, v in scores.items()}},
        )

    def _oos_scores(self, ctx: MarketContext, interval: str) -> dict[str, float]:
        """Rank enabled strategies by OUT-OF-SAMPLE robustness, not a single in-sample
        backtest. The in-sample Sharpe rewarded cost-fragile high-trade-count losers
        (vwap_trend) and noise (heikin_trend) over the genuine cost-surviving edge
        (ema_trend_fib). This is a pure SELECTION reweight — it only changes which
        already-enabled strategy is blended; it fabricates no signal and sizes nothing."""
        df = ctx.df
        try:
            bar_key = str(df.index[-1])
        except Exception:  # noqa: BLE001
            bar_key = str(len(df))
        ck = (ctx.symbol, interval)
        cached = _SEL_CACHE.get(ck)
        if cached and cached[0] == bar_key:
            return cached[1]
        scores: dict[str, float] = {}
        for sname in REGISTRY:
            if not is_enabled(sname):
                continue  # marketplace: disabled strategies are not selected
            try:
                sh = float(walk_forward(df, build_strategy(sname),
                                        interval=interval)["oos"].get("sharpe", 0.0) or 0.0)
                bt = run_backtest(df, build_strategy(sname), interval=interval)
                score = sh
                if bt.metrics["total_return"] <= 0:          # net loser over the window
                    score -= 1.0
                if not cost_stress(df, build_strategy(sname),
                                   interval=interval)["survives_2x_cost"]:
                    score -= 0.6                              # cost-fragile (the vwap_trend trap)
                rwb = monte_carlo(bt.trades).get("return_without_best_trade")
                if rwb is not None and rwb <= 0:             # one-trade-dependent, not robust
                    score -= 0.6
                scores[sname] = score
            except Exception:  # noqa: BLE001 - a broken strat must never crash selection
                scores[sname] = -99.0
        _SEL_CACHE[ck] = (bar_key, scores)
        return scores


class RiskManagerAgent(Agent):
    name = "Risk Manager"
    weight = 0.5

    def analyze(self, ctx: MarketContext) -> AgentOpinion:
        if ctx.open_positions >= settings.max_open_positions:
            return AgentOpinion(self.name, "neutral", 0.9, self.weight,
                                f"position limit reached ({settings.max_open_positions}) — no new risk",
                                veto=True)
        exp_pct = ctx.exposure_value / ctx.equity if ctx.equity else 0.0
        if exp_pct >= settings.max_portfolio_exposure_pct:
            return AgentOpinion(self.name, "neutral", 0.9, self.weight,
                                f"exposure {exp_pct:.0%} at/over cap "
                                f"{settings.max_portfolio_exposure_pct:.0%} — no new risk",
                                veto=True)
        headroom = settings.max_portfolio_exposure_pct - exp_pct
        return AgentOpinion(
            self.name, "neutral", float(min(0.7, 0.3 + headroom)), self.weight,
            f"risk headroom OK: exposure {exp_pct:.0%}, {ctx.open_positions} open positions",
            {"exposure_pct": round(exp_pct, 3)},
        )


class PortfolioOptimizerAgent(Agent):
    name = "Portfolio Optimizer"
    weight = 0.3

    def analyze(self, ctx: MarketContext) -> AgentOpinion:
        held = {p["symbol"] for p in ctx.positions}
        if ctx.symbol in held:
            return AgentOpinion(self.name, "neutral", 0.6, self.weight,
                                f"already hold {ctx.symbol} — avoid pyramiding beyond plan",
                                {"held": list(held)}, veto=True)
        same_class = sum(1 for p in ctx.positions
                         if p.get("symbol", "").endswith(ctx.symbol[-3:]))
        conc = "concentrated" if same_class >= 2 else "diversified"
        return AgentOpinion(
            self.name, "neutral", 0.5, self.weight,
            f"book is {conc}; adding {ctx.symbol} keeps diversification reasonable",
            {"held_count": len(held)},
        )


class ComplianceAgent(Agent):
    name = "Compliance & Security"
    weight = 0.0  # veto-only

    def analyze(self, ctx: MarketContext) -> AgentOpinion:
        issues: list[str] = []
        if ctx.asset_class == AssetClass.UNKNOWN.value:
            issues.append(f"cannot classify {ctx.symbol} — refuse to trade unknown instrument")
        if is_offshore_forex(ctx.symbol) and not settings.allow_offshore_forex:
            issues.append(f"{ctx.symbol}: offshore spot FX is FEMA-restricted "
                          f"(use INR pairs / NSE currency derivatives)")
        if issues:
            return AgentOpinion(self.name, "neutral", 1.0, self.weight,
                                "COMPLIANCE BLOCK: " + "; ".join(issues),
                                {"issues": issues}, veto=True)
        mode = "LIVE" if (settings.live_trading_enabled and settings.broker != "paper") else "PAPER"
        return AgentOpinion(self.name, "neutral", 1.0, self.weight,
                            f"compliance OK — execution mode: {mode}", {"mode": mode})


class ExecutorAgent:
    """Not a voter — the hands. Places a sized market order for an approved trade."""
    name = "Trade Executor"

    def execute(self, broker: BrokerAdapter, symbol: str, side: str,
                sizing: dict) -> Fill | None:
        units = sizing.get("size_units", 0.0)
        if units <= 0 or side not in ("long", "short"):
            return None
        order = Order(
            symbol=symbol,
            side=OrderSide.BUY if side == "long" else OrderSide.SELL,
            qty=units,
            stop_loss=sizing.get("stop_loss"),
            take_profit=sizing.get("take_profit"),
            meta={"sized_by": "RiskEngine"},
        )
        return broker.place_order(order)
