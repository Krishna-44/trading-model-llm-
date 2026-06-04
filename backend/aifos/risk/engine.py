"""Adaptive Risk Engine.

Every prospective trade is sized from risk-per-trade and ATR, given a hard stop
and a profit target, then checked against a battery of gates. If ANY gate fails
the trade is rejected and the system holds. The engine also owns the daily-loss
kill switch — the platform's circuit breaker.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..config import settings


@dataclass
class RiskAssessment:
    approved: bool
    side: str                       # long | short | flat
    entry: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    size_units: float = 0.0
    size_value: float = 0.0         # notional in base currency
    rr_ratio: float = 0.0
    risk_amount: float = 0.0
    reasons: list[str] = field(default_factory=list)   # why approved
    rejections: list[str] = field(default_factory=list)  # why blocked

    def to_dict(self) -> dict:
        return {
            "approved": self.approved, "side": self.side,
            "entry": round(self.entry, 4), "stop_loss": round(self.stop_loss, 4),
            "take_profit": round(self.take_profit, 4),
            "size_units": round(self.size_units, 6),
            "size_value": round(self.size_value, 2),
            "rr_ratio": round(self.rr_ratio, 2),
            "risk_amount": round(self.risk_amount, 2),
            "reasons": self.reasons, "rejections": self.rejections,
        }


class RiskEngine:
    def __init__(self) -> None:
        self.kill_switch_active = False
        self.kill_reason = ""
        self.daily_pnl = 0.0
        self.daily_start_equity = settings.starting_capital
        self.realized_trades_today = 0

    # --- circuit breaker -------------------------------------------------
    def trip_kill_switch(self, reason: str) -> None:
        self.kill_switch_active = True
        self.kill_reason = reason

    def reset_kill_switch(self) -> None:
        self.kill_switch_active = False
        self.kill_reason = ""

    def start_new_day(self, equity: float) -> None:
        self.daily_pnl = 0.0
        self.daily_start_equity = equity
        self.realized_trades_today = 0

    def register_fill(self, realized_pnl: float, equity: float) -> None:
        self.daily_pnl += realized_pnl
        self.realized_trades_today += 1
        loss_limit = -abs(self.daily_start_equity * settings.max_daily_loss_pct)
        if self.daily_pnl <= loss_limit:
            self.trip_kill_switch(
                f"daily loss {self.daily_pnl:,.0f} breached limit {loss_limit:,.0f}"
            )

    # --- core assessment -------------------------------------------------
    def assess(
        self, *, side: str, entry: float, atr: float, confidence: float,
        equity: float, open_positions: int, current_exposure_value: float,
        adv_notional: float | None = None, structure_stop: float | None = None,
    ) -> RiskAssessment:
        a = RiskAssessment(approved=False, side=side, entry=entry)

        if self.kill_switch_active:
            a.rejections.append(f"kill switch active: {self.kill_reason}")
            a.side = "flat"
            return a
        if side not in ("long", "short"):
            a.rejections.append("no directional edge -> hold")
            return a
        if confidence < settings.confidence_threshold:
            a.rejections.append(
                f"confidence {confidence:.2f} < threshold {settings.confidence_threshold:.2f}"
            )
            return a
        if open_positions >= settings.max_open_positions:
            a.rejections.append(f"max open positions ({settings.max_open_positions}) reached")
            return a
        if atr <= 0 or entry <= 0:
            a.rejections.append("invalid ATR/price — cannot size risk safely")
            return a

        # stop from ATR, optionally tightened to market structure (SMC swing level)
        stop_dist = settings.atr_stop_mult * atr
        if structure_stop and structure_stop > 0:
            sdist = abs(entry - structure_stop)
            if 0.5 * stop_dist <= sdist <= stop_dist:
                stop_dist = sdist
                a.reasons.append(f"stop tightened to market structure @ {structure_stop:.2f}")
        tgt_dist = settings.atr_target_mult * atr
        if side == "long":
            a.stop_loss, a.take_profit = entry - stop_dist, entry + tgt_dist
        else:
            a.stop_loss, a.take_profit = entry + stop_dist, entry - tgt_dist
        a.rr_ratio = tgt_dist / stop_dist if stop_dist else 0.0
        if a.rr_ratio < settings.min_rr_ratio:
            a.rejections.append(f"reward:risk {a.rr_ratio:.2f} < min {settings.min_rr_ratio}")
            return a

        # size from fixed fractional risk
        a.risk_amount = equity * settings.risk_per_trade_pct
        units = a.risk_amount / stop_dist
        notional = units * entry

        # cap by max position % and absolute per-trade cap
        cap = min(equity * settings.max_position_pct, settings.per_trade_cap)
        if notional > cap:
            scale = cap / notional
            units *= scale
            notional = units * entry
            a.reasons.append(f"size capped to {cap:,.0f} ({settings.max_position_pct:.0%}/per-trade)")

        # portfolio exposure gate
        if (current_exposure_value + notional) > equity * settings.max_portfolio_exposure_pct:
            a.rejections.append(
                f"exposure {(current_exposure_value + notional):,.0f} would exceed "
                f"{settings.max_portfolio_exposure_pct:.0%} of equity"
            )
            return a

        # liquidity / slippage guard
        if adv_notional and notional > 0.02 * adv_notional:
            scale = (0.02 * adv_notional) / notional
            units *= scale
            notional = units * entry
            a.reasons.append("size reduced for liquidity (<=2% of ADV)")

        if units <= 0 or notional <= 0:
            a.rejections.append("computed size is zero after caps")
            return a

        a.size_units = units
        a.size_value = notional
        a.approved = True
        a.reasons.insert(0, (
            f"{side} sized to risk {a.risk_amount:,.0f} ({settings.risk_per_trade_pct:.2%} of equity), "
            f"stop {a.stop_loss:.2f}, target {a.take_profit:.2f}, R:R {a.rr_ratio:.2f}"
        ))
        return a

    def snapshot(self) -> dict:
        loss_limit = self.daily_start_equity * settings.max_daily_loss_pct
        return {
            "kill_switch_active": self.kill_switch_active,
            "kill_reason": self.kill_reason,
            "daily_pnl": round(self.daily_pnl, 2),
            "daily_loss_limit": round(-loss_limit, 2),
            "daily_loss_used_pct": round(
                min(1.0, max(0.0, -self.daily_pnl / loss_limit)) if loss_limit else 0.0, 3
            ),
            "trades_today": self.realized_trades_today,
            "limits": {
                "confidence_threshold": settings.confidence_threshold,
                "max_position_pct": settings.max_position_pct,
                "max_open_positions": settings.max_open_positions,
                "max_daily_loss_pct": settings.max_daily_loss_pct,
                "min_rr_ratio": settings.min_rr_ratio,
            },
        }
