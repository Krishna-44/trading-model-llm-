"""AIFOS Kernel — the autonomous operating core.

Wires the data layer, the agent committee, the risk engine, the broker, durable
storage and the self-evaluation/memory loop into one cycle:

    build_context -> deliberate -> (risk-gated) execute -> record -> learn

Everything funnels through here so there is exactly one place that can move money
and exactly one place that decides not to (the common case).
"""
from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timezone

from .agents.base import MarketContext, TradeDecision
from .agents.committee import AgentCommittee
from .agents.governance import ExecutorAgent
from .config import settings
from .data.models import classify_asset
from .data.providers import get_provider
from .execution import get_broker
from .execution.base import LiveTradingDisabled
from .indicators import atr as atr_ind
from .memory.journal import SelfEvaluator
from .memory.vector import get_memory
from .notifications.notifier import get_notifier
from .persistence.repo import Repository
from .risk import RiskEngine

logger = logging.getLogger("aifos.kernel")


class EventBus:
    """Simple in-process ring buffer of events the WebSocket layer polls.

    Avoids cross-thread asyncio.Queue hazards: producers append, consumers track
    a sequence number and read everything newer than what they last saw."""
    def __init__(self, maxlen: int = 500) -> None:
        self._events: deque[tuple[int, dict]] = deque(maxlen=maxlen)
        self._seq = 0

    def publish(self, kind: str, payload: dict) -> None:
        self._seq += 1
        self._events.append((self._seq, {"seq": self._seq, "kind": kind,
                                         "ts": _now_iso(), **payload}))

    def since(self, last_seq: int) -> tuple[int, list[dict]]:
        new = [e for s, e in self._events if s > last_seq]
        return (self._seq, new)


class AIFOSKernel:
    def __init__(self) -> None:
        self.provider = get_provider()
        self.committee = AgentCommittee()
        self.risk = RiskEngine()
        self.broker = get_broker()          # paper unless live gate explicitly armed
        self.repo = Repository()
        self.evaluator = SelfEvaluator(self.repo)
        self.memory = get_memory()
        self.notifier = get_notifier()
        self.bus = EventBus()
        self.broker.connect()
        self.autonomous = False             # background trading loop OFF by default

    # --- context ---------------------------------------------------------
    def build_context(self, symbol: str, interval: str = "1d") -> MarketContext:
        df = self.provider.history(symbol, interval)
        df.attrs["symbol"] = symbol
        price = float(df["close"].iloc[-1])
        a = atr_ind(df["high"], df["low"], df["close"], 14).iloc[-1]
        atr_val = float(a) if a == a else 0.0  # NaN guard
        acct = self.broker.get_account()
        positions = self.broker.get_positions()
        exposure = sum(abs(p.market_value) for p in positions)
        vol = df["volume"].tail(20)
        adv = float((vol * df["close"].tail(20)).mean()) if float(vol.sum()) > 0 else None
        return MarketContext(
            symbol=symbol, asset_class=classify_asset(symbol).value, df=df, price=price,
            atr=atr_val, equity=acct.equity, open_positions=len(positions),
            exposure_value=exposure, adv_notional=adv,
            positions=[p.to_dict() for p in positions], extra={"interval": interval},
        )

    # --- decide ----------------------------------------------------------
    def analyze(self, symbol: str, interval: str = "1d", persist: bool = True) -> tuple[TradeDecision, MarketContext]:
        ctx = self.build_context(symbol, interval)
        decision = self.committee.deliberate(ctx, self.risk)
        self._remember(decision)
        if persist:
            self._persist_decision(decision)
        self.bus.publish("decision", {"decision": decision.to_dict()})
        return decision, ctx

    # --- decide + (maybe) act -------------------------------------------
    def tick(self, symbol: str, interval: str = "1d", execute: bool = True):
        decision, ctx = self.analyze(symbol, interval, persist=False)
        fill = None
        if execute and decision.action in ("BUY", "SELL") and not self.risk.kill_switch_active:
            try:
                fill = ExecutorAgent().execute(self.broker, symbol, decision.side, decision.sizing)
            except LiveTradingDisabled as exc:
                decision.reasoning += f" | execution blocked: {exc}"
                logger.warning("execution blocked: %s", exc)
            if fill:
                decision.executed = True
                acct = self.broker.get_account()
                self.risk.register_fill(fill.realized_pnl, acct.equity)
                self.repo.save_trade(
                    symbol=symbol, side=fill.side.value, qty=fill.qty, price=fill.price,
                    commission=fill.commission, realized_pnl=fill.realized_pnl,
                    order_id=fill.order_id, mode="live" if self.broker.is_live else "paper",
                )
                self.repo.save_equity(acct.equity, acct.cash)
                self.evaluator.journal_decision(decision, fill)
                self.bus.publish("fill", {"fill": fill.to_dict(), "symbol": symbol})
                self.notifier.send(f"Order filled — {symbol}",
                                   f"{fill.side.value} {fill.qty:.4f} @ {fill.price:.2f}", "info")
                if self.risk.kill_switch_active:
                    self.notifier.send("Daily loss limit breached", self.risk.kill_reason, "critical")
        self._persist_decision(decision)
        return decision, fill

    def run_universe(self, execute: bool = True) -> list[dict]:
        out = []
        for sym in settings.universe:
            try:
                decision, fill = self.tick(sym, settings.default_interval, execute=execute)
                out.append({"symbol": sym, "action": decision.action,
                            "confidence": decision.confidence, "executed": decision.executed})
            except Exception as exc:  # noqa: BLE001 - never let one symbol stop the loop
                logger.exception("tick failed for %s", sym)
                out.append({"symbol": sym, "error": str(exc)})
        try:
            self.snapshot_equity()  # one honest equity point per cycle, even when all-HOLD
        except Exception:  # noqa: BLE001
            logger.exception("equity snapshot failed")
        return out

    # --- views -----------------------------------------------------------
    def candles(self, symbol: str, interval: str = "1d", lookback: int = 240) -> dict:
        df = self.provider.history(symbol, interval).tail(lookback)
        return {
            "symbol": symbol, "interval": interval,
            "source": df.attrs.get("source", "unknown"),
            "candles": [
                {"ts": ts.isoformat(), "open": round(float(o), 4), "high": round(float(h), 4),
                 "low": round(float(low), 4), "close": round(float(cl), 4),
                 "volume": round(float(v), 2)}
                for ts, o, h, low, cl, v in zip(
                    df.index, df["open"], df["high"], df["low"], df["close"], df["volume"])
            ],
        }

    def portfolio(self) -> dict:
        acct = self.broker.get_account()
        positions = [p.to_dict() for p in self.broker.get_positions()]
        return {
            "account": acct.to_dict(),
            "positions": positions,
            "equity_curve": self.repo.equity_curve(500),
            "open_positions": len(positions),
            "unrealized_pnl": round(sum(p["unrealized_pnl"] for p in positions), 2),
            "mode": "live" if self.broker.is_live else "paper",
            "broker": self.broker.name,
        }

    def snapshot_equity(self) -> float:
        """Mark to market and persist one equity point — keeps the curve honest over
        time (captures unrealized drift) instead of only when a trade fills."""
        acct = self.broker.get_account()
        self.repo.save_equity(acct.equity, acct.cash)
        return acct.equity

    def track_record(self) -> dict:
        """Honest forward paper performance since inception — the 'prove it' view."""
        from .analytics import track_record as _build
        tr = _build(self.repo, self.broker.get_account(), settings.starting_capital)
        tr["mode"] = "live" if self.broker.is_live else "paper"
        tr["broker"] = self.broker.name
        return tr

    def risk_snapshot(self) -> dict:
        snap = self.risk.snapshot()
        snap["memory"] = self.memory.stats()
        snap["autonomous"] = self.autonomous
        return snap

    # --- controls --------------------------------------------------------
    def kill(self, reason: str = "manual kill switch") -> None:
        self.risk.trip_kill_switch(reason)
        self.autonomous = False
        self.bus.publish("control", {"event": "kill", "reason": reason})
        self.notifier.send("Kill switch tripped", reason, "critical")

    def resume(self) -> None:
        self.risk.reset_kill_switch()
        self.bus.publish("control", {"event": "resume"})

    def set_autonomous(self, on: bool) -> None:
        self.autonomous = on and not self.risk.kill_switch_active
        self.bus.publish("control", {"event": "autonomous", "on": self.autonomous})

    def reset_track_record(self) -> dict:
        """Wipe paper history and restore the starting book — 'start the clock' on a
        fresh forward test. Paper-only; refuses on a live account."""
        if self.broker.is_live:
            raise RuntimeError("refusing to reset a LIVE account")
        self.repo.reset_paper()
        if hasattr(self.broker, "reset"):
            self.broker.reset(settings.starting_capital)
        self.risk.reset_kill_switch()
        self.autonomous = False
        eq = self.snapshot_equity()  # seed the inception baseline point
        self.bus.publish("control", {"event": "track_record_reset", "equity": eq})
        return self.track_record()

    # --- internals -------------------------------------------------------
    def _persist_decision(self, d: TradeDecision) -> None:
        self.repo.save_decision(
            symbol=d.symbol, action=d.action, confidence=d.confidence, executed=d.executed,
            reasoning=d.reasoning, agent_opinions=[o.to_dict() for o in d.opinions], risk=d.risk,
        )

    def _remember(self, d: TradeDecision) -> None:
        sig = {o.agent: o.signals for o in d.opinions}
        analyst = sig.get("Market Analyst", {})
        macro = sig.get("Macro / Regime", {})
        feats = [
            float(analyst.get("rsi", 50)) / 100.0,
            float(macro.get("vol_ratio", 1.0)),
            float(analyst.get("net_score", 0.0)),
            float(d.confidence),
        ]
        self.memory.add(feats, {"symbol": d.symbol, "action": d.action,
                                "confidence": round(d.confidence, 3), "ts": _now_iso()})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_kernel: AIFOSKernel | None = None


def get_kernel() -> AIFOSKernel:
    global _kernel
    if _kernel is None:
        _kernel = AIFOSKernel()
    return _kernel
