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
        self.position_plans: dict[str, dict] = {}  # per-symbol exit plan (stop/target/trail)

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
        from .indicators.smc import smc_signals
        from .regime import detect_regime
        extra: dict = {"interval": interval}
        try:
            extra["regime"] = detect_regime(df)
            extra["smc"] = smc_signals(df)
        except Exception:  # noqa: BLE001 - context enrichment must never break a cycle
            logger.exception("regime/smc computation failed for %s", symbol)
        return MarketContext(
            symbol=symbol, asset_class=classify_asset(symbol).value, df=df, price=price,
            atr=atr_val, equity=acct.equity, open_positions=len(positions),
            exposure_value=exposure, adv_notional=adv,
            positions=[p.to_dict() for p in positions], extra=extra,
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
            if self.broker.is_live:
                ds = self.deployment()  # staged-deployment safety gate for REAL orders
                if not ds["live_permitted"]:
                    decision.reasoning += " | LIVE BLOCKED: " + "; ".join(ds["blocking"])
                    logger.warning("live execution blocked for %s: %s", symbol, ds["blocking"])
                    self._persist_decision(decision)
                    return decision, None
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
                self._record_plan(symbol, decision)
                if self.risk.kill_switch_active:
                    self.notifier.send("Daily loss limit breached", self.risk.kill_reason, "critical")
        self._persist_decision(decision)
        return decision, fill

    # --- position management (adaptive exits) ----------------------------
    def _record_plan(self, symbol: str, decision: TradeDecision) -> None:
        s = decision.sizing or {}
        entry = float(s.get("entry") or 0.0)
        stop = float(s.get("stop_loss") or 0.0)
        target = float(s.get("take_profit") or 0.0)
        if entry <= 0 or stop <= 0:
            return
        self.position_plans[symbol] = {
            "side": decision.side, "entry": entry, "stop": stop, "target": target,
            "r": abs(entry - stop) or entry * 0.01, "high_water": entry, "partial_done": False,
        }

    def _after_exit(self, symbol: str, fill, kind: str) -> None:
        acct = self.broker.get_account()
        self.risk.register_fill(fill.realized_pnl, acct.equity)
        self.repo.save_trade(
            symbol=symbol, side=fill.side.value, qty=fill.qty, price=fill.price,
            commission=fill.commission, realized_pnl=fill.realized_pnl,
            order_id=fill.order_id, mode="live" if self.broker.is_live else "paper",
        )
        self.repo.save_equity(acct.equity, acct.cash)
        self.bus.publish("fill", {"fill": fill.to_dict(), "symbol": symbol, "exit": kind})
        self.notifier.send(f"Exit · {kind} — {symbol}",
                           f"{fill.side.value} {fill.qty:.4f} @ {fill.price:.2f} "
                           f"(pnl {fill.realized_pnl:,.2f})", "info")
        self.evaluator.resolve(symbol, fill.realized_pnl)  # close the learn-from-P&L loop

    def manage_positions(self) -> list[dict]:
        """Adaptive exits on open positions each cycle: hard stop/target, partial
        profit-booking at +1R (then stop to breakeven), and a 1R trailing stop."""
        from .execution.base import Order, OrderSide
        actions: list[dict] = []
        for pos in list(self.broker.get_positions()):
            sym = pos.symbol
            plan = self.position_plans.get(sym)
            if not plan or abs(pos.qty) < 1e-9:
                continue
            try:
                px = self.broker.get_price(sym)
            except Exception:  # noqa: BLE001
                continue
            long = pos.qty > 0
            entry, r = plan["entry"], plan["r"]
            plan["high_water"] = max(plan["high_water"], px) if long else min(plan["high_water"], px)
            gain_r = ((px - entry) / r) if long else ((entry - px) / r)

            hit_stop = (long and px <= plan["stop"]) or (not long and px >= plan["stop"])
            hit_target = (long and px >= plan["target"]) or (not long and px <= plan["target"])
            if hit_stop or hit_target:
                fill = self.broker.close_position(sym)
                if fill:
                    self._after_exit(sym, fill, "stop" if hit_stop else "target")
                    actions.append({"symbol": sym, "exit": "stop" if hit_stop else "target",
                                    "pnl": round(fill.realized_pnl, 2)})
                self.position_plans.pop(sym, None)
                continue

            if gain_r >= 1.0 and not plan["partial_done"]:
                half = abs(pos.qty) / 2.0
                if half > 0:
                    side = OrderSide.SELL if long else OrderSide.BUY
                    fill = self.broker.place_order(Order(symbol=sym, side=side, qty=half))
                    if fill:
                        plan["partial_done"] = True
                        plan["stop"] = entry  # lock breakeven after booking half
                        self._after_exit(sym, fill, "partial_1R")
                        actions.append({"symbol": sym, "exit": "partial_1R",
                                        "pnl": round(fill.realized_pnl, 2)})
                continue

            if gain_r >= 1.5:
                trail = (plan["high_water"] - r) if long else (plan["high_water"] + r)
                plan["stop"] = max(plan["stop"], trail) if long else min(plan["stop"], trail)
        return actions

    def run_universe(self, execute: bool = True, interval: str | None = None) -> list[dict]:
        out = []
        interval = interval or settings.default_interval
        if execute:
            try:
                self.manage_positions()
            except Exception:  # noqa: BLE001
                logger.exception("position management failed")
        for sym in settings.universe:
            try:
                decision, fill = self.tick(sym, interval, execute=execute)
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
        contributed = float(getattr(self.broker, "contributed", settings.starting_capital))
        tr = _build(self.repo, self.broker.get_account(), contributed)
        tr["mode"] = "live" if self.broker.is_live else "paper"
        tr["broker"] = self.broker.name
        return tr

    def capital(self) -> dict:
        """Where the money is: what you put in, what's safe in cash, what's deployed."""
        acct = self.broker.get_account()
        contributed = float(getattr(self.broker, "contributed", settings.starting_capital))
        deployed = round(acct.equity - acct.cash, 2)  # value at work in open positions
        return {
            "contributed": round(contributed, 2),   # net you've added (deposits − withdrawals)
            "equity": round(acct.equity, 2),         # total value right now
            "cash": round(acct.cash, 2),             # uninvested — safe, not at risk
            "deployed": deployed,                    # at risk in positions
            "free_to_withdraw": round(acct.cash, 2), # only uninvested cash is withdrawable
            "locked": deployed,                      # close positions to free this
            "total_pnl": round(acct.equity - contributed, 2),
            "return_pct": round((acct.equity / contributed - 1) * 100, 2) if contributed else 0.0,
            "realized_pnl": round(acct.realized_pnl, 2),
            "currency": acct.currency,
            "mode": "live" if self.broker.is_live else "paper",
        }

    def deposit_funds(self, amount: float) -> dict:
        if self.broker.is_live:
            raise RuntimeError("live mode: add funds at your broker/demat account, not here")
        if not hasattr(self.broker, "deposit"):
            raise RuntimeError("this broker does not support in-app deposits")
        self.broker.deposit(float(amount))
        self.snapshot_equity()
        self.bus.publish("control", {"event": "deposit", "amount": float(amount)})
        return self.capital()

    def withdraw_funds(self, amount: float) -> dict:
        if self.broker.is_live:
            raise RuntimeError("live mode: withdraw at your broker/demat account, not here")
        if not hasattr(self.broker, "withdraw"):
            raise RuntimeError("this broker does not support in-app withdrawals")
        taken = self.broker.withdraw(float(amount))
        self.snapshot_equity()
        self.bus.publish("control", {"event": "withdraw", "amount": taken})
        out = self.capital()
        out["withdrawn"] = round(taken, 2)
        out["requested"] = round(float(amount), 2)
        return out

    def today(self) -> dict:
        """Today's booked P&L (IST trading day) and how much of the wallet is deployed."""
        from datetime import datetime, timedelta, timezone
        ist = timezone(timedelta(hours=5, minutes=30))
        day = datetime.now(ist).date()

        def _ist_date(ts: str):
            try:
                return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc).astimezone(ist).date()
            except (ValueError, TypeError):
                return None

        todays = [t for t in self.repo.recent_trades(2000) if _ist_date(t.get("ts", "")) == day]
        realized = [float(t.get("realized_pnl", 0.0) or 0.0) for t in todays]
        profit = round(sum(x for x in realized if x > 0), 2)
        loss = round(sum(x for x in realized if x < 0), 2)  # negative
        positions = self.broker.get_positions()
        unrealized = round(sum(p.to_dict().get("unrealized_pnl", 0.0) for p in positions), 2)
        cap = self.capital()
        return {
            "date": day.isoformat(),
            "profit_today": profit,
            "loss_today": loss,
            "loss_today_abs": round(abs(loss), 2),
            "booked_today": round(profit + loss, 2),
            "unrealized_pnl": unrealized,                       # real-time floating P&L (open positions)
            "open_positions": len(positions),
            "live_pnl_today": round(profit + loss + unrealized, 2),
            "trades_today": len(todays),
            "deployed": cap["deployed"],          # capital used from the wallet
            "deployed_pct": round((cap["deployed"] / cap["contributed"] * 100) if cap["contributed"] else 0.0, 2),
            "cash_idle": cap["cash"],
            "wallet": cap["contributed"],
            "currency": cap["currency"],
        }

    def explain(self, symbol: str, interval: str = "1d") -> dict:
        """Auditable reasoning tree for a fresh (non-persisted) decision: regime,
        smart-money structure, indicator alignment, the full committee, and the
        risk plan — every number traceable to why the desk would (or wouldn't) act."""
        from .indicators import adx, macd, rsi, stochastic, supertrend, vwap
        ctx = self.build_context(symbol, interval)
        decision = self.committee.deliberate(ctx, self.risk)
        df = ctx.df
        c = df["close"]
        px = float(c.iloc[-1])
        ind: dict = {}
        try:
            ind["rsi"] = round(float(rsi(c).iloc[-1]), 1)
            ind["macd_hist"] = round(float(macd(c)["hist"].iloc[-1]), 4)
            ind["adx"] = round(float(adx(df["high"], df["low"], c)["adx"].iloc[-1]), 1)
            ind["supertrend_dir"] = int(supertrend(df["high"], df["low"], c)["direction"].iloc[-1])
            ind["stoch_k"] = round(float(stochastic(df["high"], df["low"], c)["k"].iloc[-1]), 1)
            vw = float(vwap(df["high"], df["low"], c, df["volume"]).iloc[-1])
            ind["vs_vwap"] = round(px / vw - 1, 4) if vw else None
        except Exception:  # noqa: BLE001
            pass
        smc = ctx.extra.get("smc", {})
        drivers = sorted([o for o in decision.opinions if o.weight > 0 and o.stance != "neutral"],
                         key=lambda o: o.weight * o.confidence, reverse=True)
        return {
            "symbol": symbol, "price": round(px, 4),
            "decision": {"action": decision.action, "side": decision.side,
                         "confidence": round(decision.confidence, 3),
                         "reasoning": decision.reasoning, "summary": decision.llm_summary},
            "regime": ctx.extra.get("regime", {}),
            "smc": {"bias": smc.get("bias"), "score": smc.get("score"),
                    "reasoning": smc.get("reasoning"), "components": smc.get("components", {})},
            "indicators": ind,
            "agents": [o.to_dict() for o in decision.opinions],
            "drivers": [o.agent for o in drivers[:3]],
            "risk_plan": decision.risk or decision.sizing or {},
        }

    def deployment(self) -> dict:
        """Staged-deployment status + empirical go-live readiness (paper→micro→scaling)."""
        from .deployment import deployment_status
        return deployment_status(self.track_record(), self.broker.name, self.broker.is_live)

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
