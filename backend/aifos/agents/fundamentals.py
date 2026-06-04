"""Fundamentals agent — votes on equity quality + valuation using the research
layer. Abstains (weight 0) on non-equities or when no data is available, so the
committee behaves exactly as before unless real fundamentals are present."""
from __future__ import annotations

from ..research.fundamentals import get_fundamentals_client
from .base import Agent, AgentOpinion, MarketContext


class FundamentalsAgent(Agent):
    name = "Fundamentals"
    weight = 0.4

    def __init__(self) -> None:
        self.client = get_fundamentals_client()

    def analyze(self, ctx: MarketContext) -> AgentOpinion:
        f = self.client.get(ctx.symbol)
        # abstain with weight 0 -> excluded from consensus; zero impact on the core
        if not f.applicable or f.source == "none":
            return AgentOpinion(self.name, "neutral", 0.0, 0.0,
                                f.reasoning or "no fundamentals — abstaining",
                                {"applicable": f.applicable})
        return AgentOpinion(self.name, f.stance, f.confidence, self.weight, f.reasoning,
                            {"quality": round(f.quality_score, 2),
                             "value": round(f.value_score, 2),
                             "composite": round(f.composite, 2), "source": f.source})
