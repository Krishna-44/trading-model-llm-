"""Multi-Agent Coordination Layer.

Deliberation order:
  1. Strategy Evolution selects the strategy for this symbol.
  2. All agents render opinions.
  3. Any veto -> HOLD (capital protection first).
  4. Weighted directional consensus -> side + combined confidence.
  5. Risk Engine sizes the trade and applies hard gates (incl. confidence floor).
  6. LLM (if available) writes a plain-English rationale; otherwise a template.

The default outcome is HOLD. A BUY/SELL requires consensus AND risk approval AND
no veto AND confidence >= threshold.
"""
from __future__ import annotations

from ..config import settings
from ..indicators import rsi as rsi_ind
from ..memory.vector import get_memory
from ..risk import RiskEngine
from ..regime import dynamic_confidence_threshold, regime_weight_multiplier
from .analysts import (
    CandlestickAgent,
    MacroAgent,
    MarketAnalystAgent,
    NewsAgent,
    SentimentAgent,
    SmartMoneyAgent,
)
from .base import AgentOpinion, MarketContext, TradeDecision
from .fundamentals import FundamentalsAgent
from .governance import (
    ComplianceAgent,
    PortfolioOptimizerAgent,
    RiskManagerAgent,
    StrategyEvolutionAgent,
)
from .llm import get_llm

_REGIME_CODE = {"trending": 0.5, "ranging": 0.0, "volatile": -0.5, "panic": -1.0}


def _situation_features(ctx: "MarketContext", net: float) -> list[float]:
    """A compact, symbol-AGNOSTIC market-state vector for the outcome-memory:
    'when conditions looked like this, what happened?'. Describes the SETUP (RSI,
    vol regime, consensus, volatility) not the instrument, so a losing pattern on
    one symbol can suppress a similar setup on another. All components ~[-1, 1]."""
    try:
        c = ctx.df["close"]
        rsi = float(rsi_ind(c).iloc[-1]) if len(c) > 14 else 50.0
        if rsi != rsi:  # NaN guard
            rsi = 50.0
    except Exception:  # noqa: BLE001
        rsi = 50.0
    reg = ctx.extra.get("regime") or {}
    vol_ratio = float(reg.get("vol_ratio", 1.0) or 1.0)
    regime_code = _REGIME_CODE.get(reg.get("regime", "unknown"), 0.0)
    atr_pct = (ctx.atr / ctx.price) if ctx.price else 0.0
    return [(rsi - 50.0) / 50.0, max(-1.0, min(1.0, vol_ratio - 1.0)),
            float(net), regime_code, min(1.0, atr_pct * 20.0)]


_DEAD = 0.10  # legacy default; the live band is settings.consensus_dead_band (tuned to 0.20)

_SYSTEM = (
    "You are the lead strategist of an autonomous trading desk whose first rule is "
    "capital preservation. Summarize the committee's reasoning in 2-3 sentences. "
    "Be probabilistic and honest; never promise profit. If the decision is HOLD, "
    "explain what would need to change to act."
)


class AgentCommittee:
    def __init__(self) -> None:
        self.evolution = StrategyEvolutionAgent()
        self.voters = [
            MarketAnalystAgent(), SmartMoneyAgent(), CandlestickAgent(), FundamentalsAgent(),
            SentimentAgent(), NewsAgent(), MacroAgent(), RiskManagerAgent(),
            PortfolioOptimizerAgent(), ComplianceAgent(),
        ]
        self.llm = get_llm()

    def roster(self) -> list[dict]:
        agents = [self.evolution, *self.voters]
        return [{"name": a.name, "weight": a.weight,
                 "role": "advisory" if a.weight == 0 else "voter"} for a in agents]

    def deliberate(self, ctx: MarketContext, risk: RiskEngine) -> TradeDecision:
        opinions: list[AgentOpinion] = [self.evolution.analyze(ctx)]
        for agent in self.voters:
            try:
                opinions.append(agent.analyze(ctx))
            except Exception as exc:  # noqa: BLE001 - one agent must not crash the desk
                opinions.append(AgentOpinion(agent.name, "neutral", 0.0, 0.0,
                                             f"agent error: {exc}"))

        vetoes = [o for o in opinions if o.veto]

        # weighted directional consensus, with regime-adaptive weighting
        regime_info = ctx.extra.get("regime") or {}
        regime = regime_info.get("regime", "unknown")
        # regime-adaptive confidence bar: stricter in volatility/panic, looser in clean trends.
        # Marathon (aggressive paper stress test) ignores the regime tightening — it deploys
        # at the flat base bar so it actually opens multiple positions.
        eff_threshold = (settings.confidence_threshold if getattr(risk, "marathon", False)
                         else dynamic_confidence_threshold(
                             settings.confidence_threshold, regime, regime_info.get("confidence", 0.0)))
        voters = [o for o in opinions if o.weight > 0]

        def _w(o: AgentOpinion) -> float:
            return o.weight * regime_weight_multiplier(o.agent, regime)

        wsum = sum(_w(o) for o in voters) or 1.0
        net = sum(_w(o) * o.signed() for o in voters) / wsum
        confidence = float(min(0.97, abs(net)))
        dead = settings.consensus_dead_band
        side = "long" if net > dead else "short" if net < -dead else "flat"

        # situation-memory: condition confidence on how SIMILAR PAST setups resolved.
        # Haircut-ONLY — suppress setups that historically lost; never invent winners.
        sit_features: list[float] = []
        mem_note = ""
        if side != "flat":
            try:
                sit_features = _situation_features(ctx, net)
                nb = [m for m in get_memory().query(sit_features, k=8)
                      if m.get("outcome") in ("win", "loss") and m.get("similarity", 0.0) >= 0.5]
                if len(nb) >= settings.memory_min_neighbors:
                    wr = sum(1 for m in nb if m["outcome"] == "win") / len(nb)
                    if wr < 0.45:  # similar setups mostly LOST -> haircut confidence toward HOLD
                        factor = max(0.5, wr / 0.5)
                        confidence = float(confidence * factor)
                        mem_note = f" memory: {len(nb)} similar setups only {wr:.0%} won -> conf x{factor:.2f}."
            except Exception:  # noqa: BLE001 - memory must NEVER break a decision
                pass

        sizing: dict = {}
        risk_dict: dict = {}
        if vetoes:
            action, side = "HOLD", "flat"
            verdict = "HOLD — vetoed: " + "; ".join(v.reasoning for v in vetoes)
        elif side == "flat":
            action = "HOLD"
            verdict = f"HOLD — no directional edge (consensus {net:+.2f}, |net|<{dead})."
        else:
            blocked, news_reason = self._news_gate(side, confidence, opinions)
            if blocked:
                action, side = "HOLD", "flat"
                verdict = news_reason
            else:
                struct = (ctx.extra.get("smc") or {}).get("components", {}).get("structure", {})
                structure_stop = struct.get("last_swing_low") if side == "long" else struct.get("last_swing_high")
                assessment = risk.assess(
                    side=side, entry=ctx.price, atr=ctx.atr, confidence=confidence,
                    equity=ctx.equity, open_positions=ctx.open_positions,
                    current_exposure_value=ctx.exposure_value, adv_notional=ctx.adv_notional,
                    structure_stop=structure_stop, asset_class=ctx.asset_class,
                    confidence_threshold=eff_threshold,
                )
                risk_dict = assessment.to_dict()
                risk_dict["confidence_threshold"] = eff_threshold
                risk_dict["regime"] = regime
                if assessment.approved:
                    action = "BUY" if side == "long" else "SELL"
                    sizing = risk_dict
                    verdict = (f"{action} {ctx.symbol}: consensus {net:+.2f}, confidence "
                               f"{confidence:.0%}. {assessment.reasons[0] if assessment.reasons else ''}{mem_note}")
                else:
                    action, side = "HOLD", "flat"
                    verdict = "HOLD — risk gate: " + "; ".join(assessment.rejections)

        decision = TradeDecision(
            symbol=ctx.symbol, action=action, side=side, confidence=confidence,
            reasoning=verdict, opinions=opinions, risk=risk_dict, sizing=sizing,
            source=ctx.df.attrs.get("source", "unknown"),
            situation_features=sit_features,  # for outcome-memory writeback on resolve
        )
        decision.llm_summary = self._summarize(ctx, decision, net)
        return decision

    def _news_gate(self, side: str, confidence: float,
                   opinions: list[AgentOpinion]) -> tuple[bool, str]:
        """Loss-avoidance: refuse to trade INTO opposing or highly-uncertain news.
        Can only block a trade (never create one), so it strictly cuts risk."""
        news = next((o for o in opinions if o.agent == "News Intelligence" and o.weight > 0), None)
        if not news or not news.signals:
            return False, ""
        net = float(news.signals.get("net", 0.0))
        impact = float(news.signals.get("avg_impact", 0.0))
        if side == "long" and net <= -0.2 and impact >= settings.news_veto_impact:
            return True, (f"HOLD — news gate: fresh bearish headlines (net {net:+.2f}, "
                          f"impact {impact:.2f}) oppose the long setup. Not buying into bad news.")
        if side == "short" and net >= 0.2 and impact >= settings.news_veto_impact:
            return True, (f"HOLD — news gate: fresh bullish headlines (net {net:+.2f}, "
                          f"impact {impact:.2f}) oppose the short setup. Standing aside.")
        if impact >= settings.news_event_impact and confidence < settings.news_event_confidence:
            return True, (f"HOLD — news gate: high-impact event risk (impact {impact:.2f}); "
                          f"confidence {confidence:.0%} below the elevated {settings.news_event_confidence:.0%} "
                          f"bar. Waiting for clarity.")
        return False, ""

    def _summarize(self, ctx: MarketContext, decision: TradeDecision, net: float) -> str:
        bullets = "\n".join(
            f"- {o.agent} [{o.stance}, conf {o.confidence:.2f}"
            f"{', VETO' if o.veto else ''}]: {o.reasoning}" for o in decision.opinions
        )
        prompt = (
            f"Symbol: {ctx.symbol} ({ctx.asset_class}) @ {ctx.price:.2f}\n"
            f"Consensus score: {net:+.2f} | Decision: {decision.action} "
            f"({decision.confidence:.0%} confidence)\n\nCommittee opinions:\n{bullets}\n\n"
            f"Risk/sizing: {decision.sizing or 'n/a'}\n\nWrite the desk rationale."
        )
        out = self.llm.generate(prompt, system=_SYSTEM)
        if out:
            return out
        # deterministic fallback (LLM unavailable)
        drivers = sorted([o for o in decision.opinions if o.weight > 0 and o.stance != "neutral"],
                         key=lambda o: o.weight * o.confidence, reverse=True)[:2]
        lead = "; ".join(f"{o.agent} {o.stance}" for o in drivers) or "no strong directional voices"
        return (f"{decision.action} on {ctx.symbol}. Drivers: {lead}. "
                f"Combined confidence {decision.confidence:.0%}; "
                f"{'acting' if decision.action != 'HOLD' else 'holding — edge/threshold not met'}. "
                f"(Deterministic summary — no LLM connected.)")
