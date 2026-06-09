"""Portfolio-heat / directional-balance gate.

The correlation gate blocks stacking the SAME directional bet across CORRELATED
assets (short BTC while already short ETH). This gate is broader and complementary:
it caps the WHOLE book's NET long-vs-short imbalance, so the marathon cannot end
up 100% one-sided (every position short) — a posture that a single market-wide
move wipes out *regardless* of per-pair correlation. The blown-up marathon book
that prompted this was 6 positions, all short.

Gross exposure is already capped by the RiskEngine (max_portfolio_exposure_pct);
within that budget, though, the book can still be entirely one-directional. This
gate refuses a NEW open that would push net directional exposure past a hard cap
*on the side it is already skewed toward*. It can only BLOCK — never create or
resize a trade — and it always allows trades that REDUCE the imbalance (the
opposite side), so it nudges the book toward balance without forcing trades.

Settings (env-overridable):
  AIFOS_MAX_DIRECTIONAL_IMBALANCE_PCT=0.45  # |net|/equity ceiling (default 0.45)

Mirrors the shape of vol_gate / event_filter / correlation (pure, never raises).
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class HeatResult:
    blocked: bool
    reason: str = ""
    net_imbalance_pct: float = 0.0   # signed: +long / -short, as a fraction of equity
    gross_heat_pct: float = 0.0      # total deployed notional / equity (informational)

    def __bool__(self) -> bool:
        return self.blocked


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "").strip() or default)
    except Exception:  # noqa: BLE001
        return default


def check(
    side: str,
    cand_notional: float,
    positions: list[dict],
    equity: float,
    *,
    max_imbalance_pct: float | None = None,
) -> HeatResult:
    """Decide whether opening `cand_notional` of `side` ("long"/"short") would push
    the book's net directional imbalance past the cap.

    `positions` = current open book as dicts with keys ``dir`` (+1 long / -1 short)
    and ``notional`` (>=0). Returns HeatResult(blocked=True, reason=...) only when
    the candidate ADDS to the already-dominant side AND the projected |net|/equity
    exceeds the cap. Always safe — never raises."""
    if side not in ("long", "short") or cand_notional <= 0 or equity <= 0:
        return HeatResult(False)
    cap = max_imbalance_pct if max_imbalance_pct is not None else _env_float(
        "AIFOS_MAX_DIRECTIONAL_IMBALANCE_PCT", 0.45)

    long_n = sum(float(p.get("notional", 0.0)) for p in positions if p.get("dir", 0) > 0)
    short_n = sum(float(p.get("notional", 0.0)) for p in positions if p.get("dir", 0) < 0)
    cand_dir = 1 if side == "long" else -1
    proj_long = long_n + (cand_notional if cand_dir > 0 else 0.0)
    proj_short = short_n + (cand_notional if cand_dir < 0 else 0.0)

    net = proj_long - proj_short                       # signed net notional
    gross_heat = (proj_long + proj_short) / equity
    net_imbalance = net / equity                       # signed fraction of equity
    dominant_dir = 1 if net >= 0 else -1

    # Only block when the candidate ADDS to the dominant side and breaches the cap.
    # Trades on the opposite side (which REDUCE imbalance) are always allowed.
    if abs(net_imbalance) > cap and cand_dir == dominant_dir:
        dom = "long" if dominant_dir > 0 else "short"
        return HeatResult(
            True,
            f"net {dom} imbalance {abs(net_imbalance):.0%} of equity would exceed "
            f"{cap:.0%} cap — refusing to add another {side} (book too one-sided)",
            net_imbalance_pct=net_imbalance, gross_heat_pct=gross_heat,
        )
    return HeatResult(False, net_imbalance_pct=net_imbalance, gross_heat_pct=gross_heat)


__all__ = ["check", "HeatResult"]
