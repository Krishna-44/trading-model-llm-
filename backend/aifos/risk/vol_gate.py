"""Hard volatility regime gate.

`regime.py` already classifies the environment and the committee adjusts agent
weights accordingly. What's missing — and what blows up small accounts during
panic days — is a HARD stand-aside that REFUSES new opens when volatility is
elevated, regardless of how attractive a single setup looks.

This is independent of position sizing and ATR stops. Even with perfect stops,
gap risk on a panic day vapourises the position before the stop fires.

Inputs:
  • regime dict (from aifos.regime.detect_regime)
  • optional india_vix value (if you feed it; else inferred from vol_ratio)

Decision:
  • regime == "panic"                          → block (always)
  • regime == "volatile" AND vol_ratio >= 1.85 → block (stricter than the
                                                  in-committee soft trim)
  • india_vix >= threshold (default 22)        → block (regardless of regime)

Otherwise allow.

Settings can be overridden via env vars:
  AIFOS_VOL_GATE_PANIC_BLOCK=1            # default 1
  AIFOS_VOL_GATE_VOLATILE_VOL_RATIO=1.85  # default 1.85
  AIFOS_VOL_GATE_VIX_THRESHOLD=22         # default 22 (India VIX)
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class VolGateResult:
    blocked: bool
    reason: str = ""
    regime: str = ""
    vol_ratio: float = 0.0
    india_vix: float = 0.0

    def __bool__(self) -> bool:
        return self.blocked


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "").strip() or default)
    except Exception:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return default


def check(regime: dict, india_vix: float | None = None) -> VolGateResult:
    """Evaluate the gate. Returns VolGateResult(blocked=True, reason=...) when
    new opens should be refused. Always safe — never raises."""
    regime_name = (regime or {}).get("regime", "unknown")
    vol_ratio   = float((regime or {}).get("vol_ratio", 1.0) or 1.0)
    vix         = float(india_vix) if india_vix is not None else 0.0

    panic_block = _env_bool("AIFOS_VOL_GATE_PANIC_BLOCK", True)
    vr_threshold = _env_float("AIFOS_VOL_GATE_VOLATILE_VOL_RATIO", 1.85)
    vix_threshold = _env_float("AIFOS_VOL_GATE_VIX_THRESHOLD", 22.0)

    if regime_name == "panic" and panic_block:
        return VolGateResult(
            True,
            f"Regime is PANIC (vol_ratio={vol_ratio:.2f}). Stand aside — gap risk overwhelms stops.",
            regime_name, vol_ratio, vix,
        )

    if regime_name == "volatile" and vol_ratio >= vr_threshold:
        return VolGateResult(
            True,
            f"Regime VOLATILE and vol_ratio={vol_ratio:.2f} >= {vr_threshold:.2f}. New opens off.",
            regime_name, vol_ratio, vix,
        )

    if vix > 0 and vix >= vix_threshold:
        return VolGateResult(
            True,
            f"India VIX {vix:.1f} >= threshold {vix_threshold:.1f}. New opens off.",
            regime_name, vol_ratio, vix,
        )

    return VolGateResult(False, regime=regime_name, vol_ratio=vol_ratio, india_vix=vix)


__all__ = ["check", "VolGateResult"]
