"""Calendar-aware "no-trade window" gate.

Refuses to open new positions in the minutes/hours surrounding scheduled
high-impact events that historically destroy edge — RBI policy, NSE expiry,
FOMC, earnings releases. The dumbest losses are taken into known volatility.

This is a HARD gate: if the candidate's symbol or session intersects an
active window, the trade is rejected before sizing.

Calendar entries can be supplied via:
  1. The hardcoded INDIA_CALENDAR below (RBI, expiry day-of-week, etc.)
  2. settings.AIFOS_EVENT_CALENDAR_JSON pointing at a JSON file
  3. AIFOS_EXTRA_EVENTS env var (one ISO8601-start;ISO8601-end;label per line)

Tests are at backend/tests/test_event_filter.py (add when wiring up).
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
UTC = timezone.utc

# ─── Static calendar — India only ───────────────────────────────────────────
# Recurring rules. For dated events (RBI policy days, results dates), the JSON
# file or env var is the right place; this is just the perpetual stuff.

@dataclass(frozen=True)
class _WeeklyWindow:
    weekday: int        # Monday=0 ... Sunday=6
    start: time
    end: time
    label: str
    appliesTo: tuple[str, ...] = ()  # empty → all symbols

@dataclass(frozen=True)
class _DailyWindow:
    start: time
    end: time
    label: str
    appliesTo: tuple[str, ...] = ()

# NSE weekly expiry: Thursdays. Last ~90 min sees fierce option-driven moves.
# We block ALL equity / index trades in that window.
INDIA_CALENDAR_WEEKLY: tuple[_WeeklyWindow, ...] = (
    _WeeklyWindow(weekday=3, start=time(14, 0), end=time(15, 30),
                  label="NSE weekly expiry tail",
                  appliesTo=()),
)

# Around the open and close, micro-structure noise is dominant. Block first 5
# and last 5 minutes of the cash-equity session.
INDIA_CALENDAR_DAILY: tuple[_DailyWindow, ...] = (
    _DailyWindow(start=time(9, 15), end=time(9, 20), label="open auction noise"),
    _DailyWindow(start=time(15, 25), end=time(15, 30), label="closing auction noise"),
)

# ─── Dated events — RBI MPC dates for 2026 (hardcoded; update yearly) ───────
# Source: rbi.org.in/Scripts/MPCSchedule.aspx (Feb, Apr, Jun, Aug, Oct, Dec)
# Block the policy day from 09:00 to 14:00 IST.
INDIA_RBI_2026: tuple[str, ...] = (
    "2026-02-06", "2026-04-08", "2026-06-05",
    "2026-08-07", "2026-10-08", "2026-12-04",
)

# ─── Public API ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class EventFilterResult:
    blocked: bool
    label: str = ""              # "RBI MPC" / "NSE expiry tail" / ""
    window_end_utc: datetime | None = None

    def __bool__(self) -> bool:  # explicit
        return self.blocked


def is_blocked(symbol: str, now: datetime | None = None) -> EventFilterResult:
    """Return EventFilterResult(blocked=True, label=...) if a no-trade window is
    currently active for this symbol. UTC-aware throughout."""
    now = (now or datetime.now(UTC)).astimezone(UTC)
    now_ist = now.astimezone(IST)

    # 1. Daily windows (open/close noise)
    for w in INDIA_CALENDAR_DAILY:
        if w.appliesTo and not _symbol_matches(symbol, w.appliesTo):
            continue
        if w.start <= now_ist.time() <= w.end:
            end_dt = _ist_to_utc(now_ist, w.end)
            return EventFilterResult(True, w.label, end_dt)

    # 2. Weekly windows (Thursday expiry)
    for w in INDIA_CALENDAR_WEEKLY:
        if w.weekday != now_ist.weekday():
            continue
        if w.appliesTo and not _symbol_matches(symbol, w.appliesTo):
            continue
        if w.start <= now_ist.time() <= w.end:
            end_dt = _ist_to_utc(now_ist, w.end)
            return EventFilterResult(True, w.label, end_dt)

    # 3. RBI MPC dates — block 09:00–14:00 IST policy day
    today_iso = now_ist.strftime("%Y-%m-%d")
    if today_iso in INDIA_RBI_2026:
        if time(9, 0) <= now_ist.time() <= time(14, 0):
            end_dt = _ist_to_utc(now_ist, time(14, 0))
            return EventFilterResult(True, "RBI MPC policy day", end_dt)

    # 4. JSON file (optional)
    for label, start_utc, end_utc in _load_extra_events():
        if start_utc <= now <= end_utc:
            return EventFilterResult(True, label, end_utc)

    return EventFilterResult(False)


# ─── Helpers ────────────────────────────────────────────────────────────────

def _symbol_matches(symbol: str, patterns: tuple[str, ...]) -> bool:
    s = symbol.upper()
    for pat in patterns:
        if re.fullmatch(pat.upper(), s):
            return True
    return False


def _ist_to_utc(reference_dt_ist: datetime, t: time) -> datetime:
    dt_ist = reference_dt_ist.replace(hour=t.hour, minute=t.minute, second=t.second, microsecond=0)
    return dt_ist.astimezone(UTC)


def _load_extra_events() -> list[tuple[str, datetime, datetime]]:
    """Load extra dated events from env var or JSON file.
    Returns a list of (label, start_utc, end_utc) tuples. Never raises."""
    out: list[tuple[str, datetime, datetime]] = []
    raw = os.environ.get("AIFOS_EXTRA_EVENTS", "").strip()
    if raw:
        for line in raw.splitlines():
            parts = line.split(";")
            if len(parts) >= 3:
                try:
                    start = datetime.fromisoformat(parts[0]).astimezone(UTC)
                    end = datetime.fromisoformat(parts[1]).astimezone(UTC)
                    out.append((parts[2].strip(), start, end))
                except Exception:
                    pass
    path = os.environ.get("AIFOS_EVENT_CALENDAR_JSON", "")
    if path and Path(path).is_file():
        try:
            data = json.loads(Path(path).read_text())
            for item in data:
                start = datetime.fromisoformat(item["start"]).astimezone(UTC)
                end = datetime.fromisoformat(item["end"]).astimezone(UTC)
                out.append((item.get("label", "calendar event"), start, end))
        except Exception:
            pass
    return out


__all__ = ["is_blocked", "EventFilterResult"]
