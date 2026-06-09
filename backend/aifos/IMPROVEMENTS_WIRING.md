# AIFOS Pi-deployment improvements — wiring guide

This file documents the six new modules added to AIFOS as part of the Pi
deployment overnight session. They are written as drop-in additions — none of
the existing code was modified. To activate them you wire them into
`kernel.py` and `committee.py` at the points below. Each step is independent
and reversible.

## New modules

| File | Purpose | Status |
|---|---|---|
| `risk/event_filter.py` | Hard gate around known events (NSE expiry tail, RBI MPC days, open/close auction noise). | ready |
| `risk/vol_gate.py` | Hard stand-aside when regime is panic/volatile or India VIX is elevated. | ready |
| `agents/multi_timeframe.py` | Bullish only when 15m / 1h / 1d agree. Lowers confidence when they disagree. | ready |
| `agents/sector_rotation.py` | Lean into top-2 NSE sectors by relative strength, lean away from bottom-2. | ready |
| `memory/brain_sync.py` | Best-effort ingestion of decisions/outcomes into the n8n Corporate Memory Brain. | ready |
| `risk/correlation.py` | (Already existed) — directional concentration check across correlated symbols. | already wired |

## Wiring step 1 — risk gates in the kernel

In `aifos/kernel.py`, after `build_context()` and before the committee deliberates:

```python
from .risk.event_filter import is_blocked as event_blocked
from .risk.vol_gate import check as vol_gate_check

event = event_blocked(ctx.symbol)
if event.blocked:
    return TradeDecision(
        symbol=ctx.symbol, action="HOLD", side="flat", confidence=0.0,
        reasoning=f"Blocked by event window: {event.label}",
        opinions=[], source="event_filter",
    )

vol = vol_gate_check(regime)  # `regime` is the dict from regime.detect_regime
if vol.blocked:
    return TradeDecision(
        symbol=ctx.symbol, action="HOLD", side="flat", confidence=0.0,
        reasoning=f"Vol gate: {vol.reason}",
        opinions=[], source="vol_gate",
    )
```

Both gates return early without consuming LLM tokens — they're cheap and
deterministic. Put them BEFORE the committee deliberates.

## Wiring step 2 — register the new agents in the committee

In `aifos/agents/committee.py` (or wherever your `Agent` list is built):

```python
from .multi_timeframe import MultiTimeframeAgent
from .sector_rotation import SectorRotationAgent

# pass the data provider through so the agents can fetch multiple
# timeframes / sectoral indices
agents = [
    # ... existing agents ...
    MultiTimeframeAgent(provider=provider),
    SectorRotationAgent(provider=provider),
]
```

Both new agents follow the existing `Agent` contract — `analyze(ctx) -> AgentOpinion`
with `stance` in `{bullish, bearish, neutral}` and `confidence` in `[0, 1]`.

## Wiring step 3 — brain sync hook

In `aifos/kernel.py`, after a decision is finalized:

```python
from .memory.brain_sync import get_brain_sync
brain = get_brain_sync()

# fire-and-forget; never blocks
brain.record_decision(decision)
```

And in the position-close / outcome path:

```python
brain.update_outcome(decision, fill, pnl)
```

Optionally, before deliberating, the committee can recall similar prior
situations:

```python
prior = brain.recall_similar(ctx.symbol,
                             f"Last AIFOS decisions on {ctx.symbol} similar setup",
                             limit=3)
# Pass as extra context into the LLM agents' prompt.
```

Defaults to `http://pi5.local:5678` — override with `AIFOS_BRAIN_URL`.

## Env vars introduced

| Var | Default | Purpose |
|---|---|---|
| `AIFOS_BRAIN_URL` | `http://pi5.local:5678` | Where the n8n brain lives |
| `AIFOS_BRAIN_AUTH_HEADER` / `AIFOS_BRAIN_AUTH_VALUE` | unset | Optional header auth |
| `AIFOS_VOL_GATE_PANIC_BLOCK` | `1` | Hard-block opens in panic regime |
| `AIFOS_VOL_GATE_VOLATILE_VOL_RATIO` | `1.85` | Threshold for volatile-regime block |
| `AIFOS_VOL_GATE_VIX_THRESHOLD` | `22.0` | India VIX block threshold |
| `AIFOS_EXTRA_EVENTS` | unset | Add ad-hoc no-trade windows (line-separated `ISO_START;ISO_END;label`) |
| `AIFOS_EVENT_CALENDAR_JSON` | unset | Path to JSON file of dated events |

## Tests to add (not written yet — TODO)

- `backend/tests/test_event_filter.py` — verify Thursday 14:00 IST blocks, RBI day blocks, off-window allows
- `backend/tests/test_vol_gate.py` — panic blocks, volatile + vol_ratio>=1.85 blocks, vix threshold
- `backend/tests/test_multi_timeframe.py` — all-bullish → bullish/high-conf, mixed → neutral/low-conf
- `backend/tests/test_sector_rotation.py` — top-rank → bullish, bottom-rank → bearish, unknown symbol → neutral

## What's intentionally NOT changed

- The existing `regime.py` weight multiplier remains the soft layer; the new
  `vol_gate.py` is a hard layer on top. Soft trim still happens in normal
  regimes.
- `risk/correlation.py` is untouched — already does what task #20 asked for.
- The live-trading gate is NOT modified. `AIFOS_LIVE_TRADING_ENABLED=false`
  stays the default. These improvements affect paper-trading behaviour only
  until you explicitly flip the live gate.
