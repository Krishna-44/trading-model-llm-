"""Thin repository over the ORM. All reads return plain dicts ready for the API."""
from __future__ import annotations

from sqlalchemy import desc, select

from .db import get_session
from .models import DecisionRecord, EquityPoint, JournalEntry, TradeRecord


def _row(obj) -> dict:
    d = {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
    if "ts" in d and d["ts"] is not None:
        d["ts"] = d["ts"].isoformat()
    return d


class Repository:
    def save_decision(self, **kw) -> int:
        with get_session() as s:
            rec = DecisionRecord(**kw)
            s.add(rec)
            s.flush()
            return rec.id

    def save_trade(self, **kw) -> int:
        with get_session() as s:
            rec = TradeRecord(**kw)
            s.add(rec)
            s.flush()
            return rec.id

    def save_equity(self, equity: float, cash: float) -> None:
        with get_session() as s:
            s.add(EquityPoint(equity=equity, cash=cash))

    def save_journal(self, **kw) -> int:
        with get_session() as s:
            rec = JournalEntry(**kw)
            s.add(rec)
            s.flush()
            return rec.id

    def recent_decisions(self, limit: int = 50) -> list[dict]:
        with get_session() as s:
            rows = s.execute(
                select(DecisionRecord).order_by(desc(DecisionRecord.ts)).limit(limit)
            ).scalars().all()
            return [_row(r) for r in rows]

    def recent_trades(self, limit: int = 100) -> list[dict]:
        with get_session() as s:
            rows = s.execute(
                select(TradeRecord).order_by(desc(TradeRecord.ts)).limit(limit)
            ).scalars().all()
            return [_row(r) for r in rows]

    def equity_curve(self, limit: int = 500) -> list[dict]:
        with get_session() as s:
            rows = s.execute(
                select(EquityPoint).order_by(EquityPoint.ts).limit(limit)
            ).scalars().all()
            return [_row(r) for r in rows]

    def recent_journal(self, limit: int = 50) -> list[dict]:
        with get_session() as s:
            rows = s.execute(
                select(JournalEntry).order_by(desc(JournalEntry.ts)).limit(limit)
            ).scalars().all()
            return [_row(r) for r in rows]
