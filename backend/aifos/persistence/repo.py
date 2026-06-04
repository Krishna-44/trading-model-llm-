"""Thin repository over the ORM. All reads return plain dicts ready for the API."""
from __future__ import annotations

from sqlalchemy import delete, desc, func, select

from .db import get_session
from .models import (
    DecisionRecord,
    EquityPoint,
    ExtractedStrategyRecord,
    JournalEntry,
    OptionPositionRecord,
    TradeRecord,
    VideoJobRecord,
)


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

    def resolve_open_journal(self, symbol: str, outcome: str, lesson: str) -> None:
        """Resolve the latest still-open journal entry for a symbol to a win/loss."""
        with get_session() as s:
            row = s.execute(
                select(JournalEntry)
                .where(JournalEntry.symbol == symbol, JournalEntry.outcome == "open")
                .order_by(desc(JournalEntry.ts)).limit(1)
            ).scalars().first()
            if row:
                row.outcome = outcome
                row.lesson = lesson

    # --- track-record aggregates ----------------------------------------
    def count_decisions(self) -> int:
        with get_session() as s:
            return int(s.execute(select(func.count()).select_from(DecisionRecord)).scalar() or 0)

    def count_executed(self) -> int:
        with get_session() as s:
            return int(s.execute(
                select(func.count()).select_from(DecisionRecord)
                .where(DecisionRecord.executed.is_(True))
            ).scalar() or 0)

    def inception_ts(self) -> str | None:
        """Oldest timestamp on record — when this forward run's clock started."""
        with get_session() as s:
            d = s.execute(select(func.min(DecisionRecord.ts))).scalar()
            e = s.execute(select(func.min(EquityPoint.ts))).scalar()
        cands = [x for x in (d, e) if x is not None]
        return min(cands).isoformat() if cands else None

    def reset_paper(self) -> None:
        """Wipe all paper history — decisions, trades, equity curve, journal, options."""
        with get_session() as s:
            for model in (DecisionRecord, TradeRecord, EquityPoint, JournalEntry, OptionPositionRecord):
                s.execute(delete(model))

    # --- paper options lab persistence ----------------------------------
    def save_option(self, **kw) -> int:
        with get_session() as s:
            rec = OptionPositionRecord(**kw)
            s.add(rec)
            s.flush()
            return rec.id

    def open_options(self) -> list[dict]:
        with get_session() as s:
            rows = s.execute(
                select(OptionPositionRecord)
                .where(OptionPositionRecord.status == "open")
                .order_by(OptionPositionRecord.ts)
            ).scalars().all()
            return [_row(r) for r in rows]

    def close_option(self, oid: int, realized_pnl: float) -> None:
        with get_session() as s:
            row = s.get(OptionPositionRecord, int(oid))
            if row:
                row.status = "closed"
                row.realized_pnl = realized_pnl

    # --- extracted strategies (n8n video pipeline) ----------------------
    def save_extracted(self, **kw) -> int:
        with get_session() as s:
            rec = ExtractedStrategyRecord(**kw)
            s.add(rec)
            s.flush()
            return rec.id

    def list_extracted(self, limit: int = 50) -> list[dict]:
        with get_session() as s:
            rows = s.execute(
                select(ExtractedStrategyRecord).order_by(desc(ExtractedStrategyRecord.ts)).limit(limit)
            ).scalars().all()
            return [_row(r) for r in rows]

    # --- video job queue (the dashboard table n8n is wired to) ----------
    def save_video(self, url: str, title: str = "") -> int:
        with get_session() as s:
            rec = VideoJobRecord(url=url, title=title)
            s.add(rec)
            s.flush()
            return rec.id

    def list_videos(self, limit: int = 50) -> list[dict]:
        with get_session() as s:
            rows = s.execute(
                select(VideoJobRecord).order_by(desc(VideoJobRecord.ts)).limit(limit)
            ).scalars().all()
            return [_row(r) for r in rows]

    def claim_queued_videos(self, limit: int = 5) -> list[dict]:
        """Atomically hand out queued jobs to a poller (queued -> processing) so the
        same link is never processed twice. Returns the claimed rows."""
        with get_session() as s:
            rows = s.execute(
                select(VideoJobRecord)
                .where(VideoJobRecord.status == "queued")
                .order_by(VideoJobRecord.ts).limit(limit)
            ).scalars().all()
            claimed = []
            for r in rows:
                r.status = "processing"
                claimed.append(_row(r))
            return claimed

    def update_video(self, vid: int, **kw) -> None:
        with get_session() as s:
            row = s.get(VideoJobRecord, int(vid))
            if row:
                for k, v in kw.items():
                    setattr(row, k, v)
