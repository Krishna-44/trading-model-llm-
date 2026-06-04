"""Staged live-trading safety pipeline + empirical go-live readiness.

Real money is EARNED, not switched on. The pipeline is paper -> micro -> scaling,
and a LIVE order is blocked unless the forward paper track record clears every
readiness gate AND the stage + master switch + a real broker all permit it.

Nothing here fakes performance — the gates read the real track record. This is
the system's promise that it will not risk capital it has not yet earned the
right to risk.
"""
from __future__ import annotations

from .config import settings

STAGES = {
    "paper":   {"order": 0, "label": "Paper only", "live": False,
                "desc": "Forward paper trading on live data. No real money is at risk."},
    "micro":   {"order": 1, "label": "Micro capital", "live": True,
                "desc": "Tiny real positions, strict per-trade and daily-loss caps."},
    "scaling": {"order": 2, "label": "Adaptive scaling", "live": True,
                "desc": "Scale capital gradually, only while empirical results hold."},
}


def evaluate_readiness(tr: dict) -> dict:
    """Score the forward paper track record against the go-live thresholds."""
    def gate(name: str, value: float, op: str, threshold: float, unit: str = "") -> dict:
        ok = (value >= threshold) if op == ">=" else (value <= threshold) if op == "<=" else False
        return {"name": name, "pass": bool(ok), "value": value,
                "threshold": threshold, "op": op, "unit": unit}

    gates = [
        gate("Forward-test duration", round(tr.get("days_running", 0.0), 1), ">=", settings.golive_min_days, "days"),
        gate("Closed trades", tr.get("closed_trades", 0), ">=", settings.golive_min_closed_trades, ""),
        gate("Positive expectancy", tr.get("expectancy", 0.0), ">=", settings.golive_min_expectancy, "₹"),
        gate("Sharpe ratio", tr.get("sharpe", 0.0), ">=", settings.golive_min_sharpe, ""),
        gate("Profit factor", tr.get("profit_factor", 0.0), ">=", settings.golive_min_profit_factor, ""),
        gate("Max drawdown", round(abs(tr.get("max_drawdown", 0.0)), 4), "<=", settings.golive_max_drawdown, "frac"),
    ]
    passed = sum(1 for g in gates if g["pass"])
    return {"ready": passed == len(gates), "passed": passed, "total": len(gates), "gates": gates}


def live_execution_allowed(readiness_ready: bool) -> tuple[bool, list[str]]:
    """The hard gate consulted before any LIVE order leaves the system."""
    blocking: list[str] = []
    stage = settings.deployment_stage if settings.deployment_stage in STAGES else "paper"
    if not settings.live_trading_enabled:
        blocking.append("master switch live_trading_enabled is OFF")
    if STAGES[stage]["order"] == 0:
        blocking.append(f"deployment_stage '{stage}' does not permit live orders")
    if settings.broker == "paper":
        blocking.append("no real broker connected (broker = paper)")
    if not readiness_ready:
        blocking.append("go-live readiness gates not all passed")
    return (len(blocking) == 0, blocking)


def deployment_status(tr: dict, broker_name: str, is_live: bool) -> dict:
    stage = settings.deployment_stage if settings.deployment_stage in STAGES else "paper"
    readiness = evaluate_readiness(tr)
    permitted, blocking = live_execution_allowed(readiness["ready"])
    return {
        "stage": stage,
        "stage_label": STAGES[stage]["label"],
        "stage_desc": STAGES[stage]["desc"],
        "stages": [{"key": k, **v} for k, v in sorted(STAGES.items(), key=lambda x: x[1]["order"])],
        "live_trading_enabled": settings.live_trading_enabled,
        "broker": broker_name,
        "is_live": is_live,
        "mode": "live" if is_live else "paper",
        "readiness": readiness,
        "live_permitted": permitted,           # would a live order be allowed right now?
        "blocking": blocking,                  # ...and if not, exactly why
        "micro_caps": {"max_risk_per_trade": settings.micro_max_risk_per_trade,
                       "max_daily_loss": settings.micro_max_daily_loss},
        "note": "Real money is earned. Live execution stays blocked until every gate clears.",
    }
