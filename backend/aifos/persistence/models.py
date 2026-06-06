"""ORM models — the system's durable memory of what it decided, did, and learned."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DecisionRecord(Base):
    __tablename__ = "decisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    action: Mapped[str] = mapped_column(String(8))          # BUY | SELL | HOLD
    confidence: Mapped[float] = mapped_column(Float)
    executed: Mapped[bool] = mapped_column(Boolean, default=False)
    reasoning: Mapped[str] = mapped_column(Text, default="")
    agent_opinions: Mapped[dict] = mapped_column(JSON, default=dict)
    risk: Mapped[dict] = mapped_column(JSON, default=dict)


class TradeRecord(Base):
    __tablename__ = "trades"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    side: Mapped[str] = mapped_column(String(8))
    qty: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    commission: Mapped[float] = mapped_column(Float, default=0.0)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    order_id: Mapped[str] = mapped_column(String(64), default="")
    mode: Mapped[str] = mapped_column(String(8), default="paper")  # paper | live
    strategy: Mapped[str] = mapped_column(String(32), default="")  # which strategy produced it


class EquityPoint(Base):
    __tablename__ = "equity_curve"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    equity: Mapped[float] = mapped_column(Float)
    cash: Mapped[float] = mapped_column(Float)


class JournalEntry(Base):
    """Self-critique: what the system predicted vs what happened, and the lesson."""
    __tablename__ = "journal"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    decision_id: Mapped[int] = mapped_column(Integer, default=0)
    predicted: Mapped[dict] = mapped_column(JSON, default=dict)
    actual: Mapped[dict] = mapped_column(JSON, default=dict)
    outcome: Mapped[str] = mapped_column(String(16), default="open")  # win|loss|flat|open
    lesson: Mapped[str] = mapped_column(Text, default="")


class OptionPositionRecord(Base):
    """A paper options-lab strategy position (model-priced; survives restarts)."""
    __tablename__ = "option_positions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)  # opened
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    strategy: Mapped[str] = mapped_column(String(32))
    label: Mapped[str] = mapped_column(String(48), default="")
    legs: Mapped[list] = mapped_column(JSON, default=list)
    entry_spot: Mapped[float] = mapped_column(Float, default=0.0)
    entry_net: Mapped[float] = mapped_column(Float, default=0.0)
    days_at_open: Mapped[int] = mapped_column(Integer, default=7)
    vol: Mapped[float] = mapped_column(Float, default=0.2)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)   # max_profit/max_loss/breakevens
    status: Mapped[str] = mapped_column(String(8), default="open")  # open | closed
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0)


class ExtractedStrategyRecord(Base):
    """A strategy extracted from a video transcript (via n8n), pending human review."""
    __tablename__ = "extracted_strategies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    source: Mapped[str] = mapped_column(String(256), default="")
    strategy_name: Mapped[str] = mapped_column(String(96), default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    mapped_template: Mapped[str] = mapped_column(String(32), default="")
    clarity: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(12), default="review")  # review | approved | rejected


class VideoJobRecord(Base):
    """A submitted video link — the dashboard queue the n8n pipeline reads from and
    writes results back to. Lifecycle: queued -> processing -> done | error."""
    __tablename__ = "video_jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    url: Mapped[str] = mapped_column(String(512), default="")
    title: Mapped[str] = mapped_column(String(160), default="")
    status: Mapped[str] = mapped_column(String(12), default="queued")  # queued|processing|done|error
    note: Mapped[str] = mapped_column(String(256), default="")
    extracted_id: Mapped[int] = mapped_column(Integer, default=0)  # -> extracted_strategies.id


class CookingResult(Base):
    """One round of strategy "cooking" — a backtest + MC evaluation of a parameter
    variant on the multi-market basket. Append-only history feeds the leaderboard."""
    __tablename__ = "cooking_results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    variant_id: Mapped[str] = mapped_column(String(96), index=True)  # base_strategy + param signature
    base: Mapped[str] = mapped_column(String(32))
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    avg_return: Mapped[float] = mapped_column(Float, default=0.0)
    markets_positive: Mapped[int] = mapped_column(Integer, default=0)
    mc_robust_count: Mapped[int] = mapped_column(Integer, default=0)
    markets_tested: Mapped[int] = mapped_column(Integer, default=0)
    verdict: Mapped[str] = mapped_column(String(12), default="REVIEW")  # KEEP / REVIEW / DROP
    note: Mapped[str] = mapped_column(String(240), default="")


class PaperBrokerState(Base):
    """Singleton snapshot (id=1) of the paper broker — cash + open positions — so the
    live book survives restarts/reboots. True 24/7 continuity for the forward test."""
    __tablename__ = "paper_broker_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    cash: Mapped[float] = mapped_column(Float, default=0.0)
    contributed: Mapped[float] = mapped_column(Float, default=0.0)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    positions: Mapped[list] = mapped_column(JSON, default=list)  # [{symbol, qty, avg_price}]


class StrategyStateRecord(Base):
    """Persisted enabled/disabled flag per strategy, so manual toggles and Monte
    Carlo enforcement survive restarts (a fragile strategy stays disabled)."""
    __tablename__ = "strategy_state"
    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
