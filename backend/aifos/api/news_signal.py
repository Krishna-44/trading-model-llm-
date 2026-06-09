"""News-signal ingestion endpoint.

Receives sentiment-scored headlines from the n8n news-pipeline workflow on Pi
(see ~/brain-pi-bundle/workflows/news-sentiment-pipeline.json). Stores them in
an in-process ring buffer and exposes:

  POST /api/news-signal     — ingest one scored headline
  GET  /api/news-signal     — get the most recent N headlines (default 20)
  GET  /api/news-signal/by-symbol/{symbol}   — recent headlines for a symbol
  GET  /api/news-signal/by-sector/{sector}   — recent headlines for a sector

The signal is also retrievable as **context** by the committee's News /
Sentiment agent via `get_recent_signals(symbol)`.

This is a deliberate light-touch implementation:
  - in-memory ring buffer (no Postgres write) — restart loses recent signals
  - if you want durability, persist via the brain (the n8n workflow already does)
  - keep the hot path fast: news adds context, doesn't gate decisions

Mount via aifos/api/app.py:

    from .news_signal import router as news_signal_router
    app.include_router(news_signal_router)
"""
from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

MAX_SIGNALS = 500  # ring buffer size


# ─── pydantic schema for incoming POST ─────────────────────────────────────

class NewsSignalIn(BaseModel):
    subject: str = Field(..., description="Primary symbol or sector affected")
    raw_text: str = Field(..., description="Original headline + sentiment summary")
    importance: float = Field(0.5, ge=0.0, le=1.0)
    event_type: str = Field("observation")
    source: str = Field("news")
    metadata: dict[str, Any] = Field(default_factory=dict)


class NewsSignalOut(NewsSignalIn):
    ingested_at: datetime


# ─── ring buffer ────────────────────────────────────────────────────────────

@dataclass
class _Store:
    buf: deque = field(default_factory=lambda: deque(maxlen=MAX_SIGNALS))

    def add(self, signal: NewsSignalIn) -> NewsSignalOut:
        record = NewsSignalOut(**signal.dict(),
                               ingested_at=datetime.now(timezone.utc))
        self.buf.append(record)
        return record

    def recent(self, limit: int = 20) -> list[NewsSignalOut]:
        return list(self.buf)[-limit:][::-1]

    def by_symbol(self, symbol: str, limit: int = 20) -> list[NewsSignalOut]:
        s = symbol.upper()
        out = [r for r in self.buf
               if s == r.subject.upper()
               or s in (r.metadata.get("affected_symbols") or [])]
        return out[-limit:][::-1]

    def by_sector(self, sector: str, limit: int = 20) -> list[NewsSignalOut]:
        sec = sector.lower()
        out = [r for r in self.buf
               if sec == r.subject.lower()
               or sec in (r.metadata.get("affected_sectors") or [])]
        return out[-limit:][::-1]


_store = _Store()


# ─── FastAPI router ─────────────────────────────────────────────────────────

router = APIRouter(prefix="/api/news-signal", tags=["news"])


@router.post("", response_model=NewsSignalOut)
def ingest(signal: NewsSignalIn) -> NewsSignalOut:
    """Receive one scored headline from the n8n news pipeline."""
    return _store.add(signal)


@router.get("", response_model=list[NewsSignalOut])
def recent(limit: int = 20) -> list[NewsSignalOut]:
    """Most-recent ingested signals (newest first)."""
    if limit < 1 or limit > MAX_SIGNALS:
        raise HTTPException(400, f"limit must be 1..{MAX_SIGNALS}")
    return _store.recent(limit)


@router.get("/by-symbol/{symbol}", response_model=list[NewsSignalOut])
def by_symbol(symbol: str, limit: int = 20) -> list[NewsSignalOut]:
    return _store.by_symbol(symbol, limit)


@router.get("/by-sector/{sector}", response_model=list[NewsSignalOut])
def by_sector(sector: str, limit: int = 20) -> list[NewsSignalOut]:
    return _store.by_sector(sector, limit)


# ─── accessor for in-process consumers (e.g., the News agent) ─────────────

def get_recent_signals(symbol: str | None = None, limit: int = 10) -> list[dict]:
    """Used by the News/Sentiment committee agent to fold news context into
    its vote. Returns plain dicts to keep cross-module coupling small."""
    if symbol:
        recs = _store.by_symbol(symbol, limit)
    else:
        recs = _store.recent(limit)
    return [r.dict() for r in recs]


__all__ = ["router", "NewsSignalIn", "NewsSignalOut", "get_recent_signals"]
