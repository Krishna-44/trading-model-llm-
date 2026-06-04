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
