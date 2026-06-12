"""Agent contracts and the decision object passed across the system."""
from __future__ import annotations

import abc
from dataclasses import dataclass, field

import pandas as pd

STANCE_SIGN = {"bullish": 1.0, "bearish": -1.0, "neutral": 0.0}


@dataclass
class MarketContext:
    symbol: str
    asset_class: str
    df: pd.DataFrame
    price: float
    atr: float
    equity: float
    open_positions: int = 0
    exposure_value: float = 0.0
    adv_notional: float | None = None
    positions: list[dict] = field(default_factory=list)
    extra: dict = field(default_factory=dict)


@dataclass
class AgentOpinion:
    agent: str
    stance: str               # bullish | bearish | neutral
    confidence: float         # 0..1 conviction in THIS agent's read
    weight: float             # importance in the consensus
    reasoning: str
    signals: dict = field(default_factory=dict)
    veto: bool = False        # hard block regardless of consensus

    def signed(self) -> float:
        return STANCE_SIGN.get(self.stance, 0.0) * max(0.0, min(1.0, self.confidence))

    def to_dict(self) -> dict:
        return {
            "agent": self.agent, "stance": self.stance,
            "confidence": round(self.confidence, 3), "weight": self.weight,
            "reasoning": self.reasoning, "signals": self.signals, "veto": self.veto,
        }


@dataclass
class TradeDecision:
    symbol: str
    action: str               # BUY | SELL | HOLD
    side: str                 # long | short | flat
    confidence: float
    reasoning: str
    opinions: list[AgentOpinion]
    risk: dict = field(default_factory=dict)
    sizing: dict = field(default_factory=dict)
    executed: bool = False
    llm_summary: str = ""
    source: str = "unknown"
    situation_features: list = field(default_factory=list)  # market-state vector for outcome-memory writeback

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol, "action": self.action, "side": self.side,
            "confidence": round(self.confidence, 3), "reasoning": self.reasoning,
            "llm_summary": self.llm_summary, "source": self.source,
            "executed": self.executed,
            "opinions": [o.to_dict() for o in self.opinions],
            "risk": self.risk, "sizing": self.sizing,
        }


class Agent(abc.ABC):
    name: str = "agent"
    weight: float = 0.0       # 0 => advisory/veto-only, doesn't vote direction

    @abc.abstractmethod
    def analyze(self, ctx: MarketContext) -> AgentOpinion: ...
