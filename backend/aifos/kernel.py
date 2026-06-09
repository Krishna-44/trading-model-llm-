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
from pathlib import Path

from .agents.base import MarketContext, TradeDecision
from .agents.committee import AgentCommittee
from .agents.governance import ExecutorAgent
from .config import settings
from .data.models import classify_asset
from .data.providers import get_provider
from .execution import BadQuoteError, get_broker
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
        try:
            self.broker.connect()
        except Exception:  # noqa: BLE001 - a broker connection issue must never crash the app
            logger.exception("broker '%s' connect failed (will retry on demand)", self.broker.name)
        self.autonomous = False             # background trading loop OFF by default
        self.position_plans: dict[str, dict] = {}  # per-symbol exit plan (stop/target/trail)
        self.option_book: dict = {}                 # paper options strategies (mirrors DB)
        self._load_options()
        self._load_broker_state()   # rehydrate paper cash + open positions across restarts
        self._load_strategy_state()  # apply persisted enabled/disabled flags (MC enforcement sticks)

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
        from .indicators.candles import candle_read
        from .indicators.smc import smc_signals
        from .regime import detect_regime
        extra: dict = {"interval": interval}
        try:
            extra["regime"] = detect_regime(df)
            extra["smc"] = smc_signals(df)
            extra["candles"] = candle_read(df)
        except Exception:  # noqa: BLE001 - context enrichment must never break a cycle
            logger.exception("regime/smc/candles computation failed for %s", symbol)
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

    def _correlation_gate(self, symbol: str, decision, interval: str) -> str | None:
        """Block a trade that would STACK the same directional bet across correlated
        assets (e.g. short BTC while already short ETH). Returns a reason or None.
        Survivability gate — it can only block, never create or resize a trade."""
        sizing = decision.sizing or {}
        cand_notional = float(sizing.get("size_value") or 0.0)
        if cand_notional <= 0 or decision.side not in ("long", "short"):
            return None
        try:
            pf = self.portfolio()
        except Exception:  # noqa: BLE001
            return None
        poss = [{"symbol": p["symbol"], "dir": 1 if p["qty"] > 0 else -1,
                 "notional": abs(p["qty"]) * float(p.get("avg_price") or 0.0)}
                for p in pf.get("positions", []) if p.get("symbol") and p.get("qty")]
        if not poss:
            return None
        from .risk.correlation import aligned_correlated
        cand_dir = 1 if decision.side == "long" else -1
        aligned, combined = aligned_correlated(
            self.provider, symbol, cand_dir, cand_notional, poss,
            interval=interval, threshold=settings.correlation_threshold,
            lookback=settings.correlation_lookback)
        if not aligned:
            return None
        names = ", ".join(f"{a['symbol']} ρ{a['corr']:+.2f}" for a in aligned)
        if len(aligned) >= settings.max_correlated_positions:
            return (f"already holding {len(aligned)} correlated {decision.side} "
                    f"position(s) [{names}] — refusing to stack the same bet")
        equity = float(pf.get("account", {}).get("equity") or settings.starting_capital)
        cap = equity * settings.max_correlated_exposure_pct
        if combined > cap:
            return (f"combined correlated {decision.side} exposure {combined:,.0f} > "
                    f"{settings.max_correlated_exposure_pct:.0%} equity cap [{names}]")
        return None

    def _safety_gates(self, symbol: str, ctx) -> str | None:
        """Hard block-only stand-aside gates checked before any order: (1) no-trade
        event windows (NSE expiry tail, open/close auction, RBI MPC days — NSE
        symbols only), and (2) volatility-regime gate (panic/volatile/high-VIX).
        Both can only refuse a trade, never create one. Never raises."""
        try:
            from .risk.event_filter import is_blocked as event_blocked
            from .risk.vol_gate import check as vol_check
            is_nse = symbol.upper().endswith((".NS", ".BO")) or symbol.upper().startswith("^NSE")
            if is_nse:
                ev = event_blocked(symbol)
                if ev.blocked:
                    return f"EVENT GATE: {ev.label}"
            vg = vol_check((ctx.extra or {}).get("regime") or {})
            if vg.blocked:
                return f"VOL GATE: {vg.reason}"
        except Exception:  # noqa: BLE001 - a safety gate must never break trading
            logger.exception("safety gate check failed")
        return None

    # --- decide + (maybe) act -------------------------------------------
    def tick(self, symbol: str, interval: str = "1d", execute: bool = True):
        decision, ctx = self.analyze(symbol, interval, persist=False)
        strategy = ctx.extra.get("strategy_name", "")
        fill = None
        if execute and decision.action in ("BUY", "SELL") and not self.risk.kill_switch_active:
            stand_aside = self._safety_gates(symbol, ctx)  # block-only: event window + vol regime
            if stand_aside:
                decision.reasoning += f" | {stand_aside}"
                logger.info("safety gate held %s: %s", symbol, stand_aside)
                self._persist_decision(decision)
                return decision, None
            corr_block = self._correlation_gate(symbol, decision, interval)
            if corr_block:  # don't stack the same directional bet across correlated assets
                decision.reasoning += f" | CORRELATION GATE: {corr_block}"
                logger.info("correlation gate held %s: %s", symbol, corr_block)
                self._persist_decision(decision)
                return decision, None
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
            except BadQuoteError as exc:
                decision.reasoning += f" | BAD-TICK GUARD: {exc}"
                logger.error("refused to fill %s on a corrupt quote: %s", symbol, exc)
            if fill:
                decision.executed = True
                acct = self.broker.get_account()
                self.risk.register_fill(fill.realized_pnl, acct.equity)
                self.repo.save_trade(
                    symbol=symbol, side=fill.side.value, qty=fill.qty, price=fill.price,
                    commission=fill.commission, realized_pnl=fill.realized_pnl,
                    order_id=fill.order_id, mode="live" if self.broker.is_live else "paper",
                    strategy=strategy,
                )
                self.repo.save_equity(acct.equity, acct.cash)
                self.evaluator.journal_decision(decision, fill)
                self.bus.publish("fill", {"fill": fill.to_dict(), "symbol": symbol})
                self.notifier.send(f"Order filled — {symbol}",
                                   f"{fill.side.value} {fill.qty:.4f} @ {fill.price:.2f}", "info")
                self._record_plan(symbol, decision, strategy)
                if self.risk.kill_switch_active:
                    self.notifier.send("Daily loss limit breached", self.risk.kill_reason, "critical")
        self._persist_decision(decision)
        return decision, fill

    # --- position management (adaptive exits) ----------------------------
    def _record_plan(self, symbol: str, decision: TradeDecision, strategy: str = "") -> None:
        s = decision.sizing or {}
        entry = float(s.get("entry") or 0.0)
        stop = float(s.get("stop_loss") or 0.0)
        target = float(s.get("take_profit") or 0.0)
        if entry <= 0 or stop <= 0:
            return
        self.position_plans[symbol] = {
            "side": decision.side, "entry": entry, "stop": stop, "target": target,
            "r": abs(entry - stop) or entry * 0.01, "high_water": entry, "partial_done": False,
            "strategy": strategy,
        }

    def _after_exit(self, symbol: str, fill, kind: str) -> None:
        acct = self.broker.get_account()
        self.risk.register_fill(fill.realized_pnl, acct.equity)
        self.repo.save_trade(
            symbol=symbol, side=fill.side.value, qty=fill.qty, price=fill.price,
            commission=fill.commission, realized_pnl=fill.realized_pnl,
            order_id=fill.order_id, mode="live" if self.broker.is_live else "paper",
            strategy=(self.position_plans.get(symbol) or {}).get("strategy", ""),
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
                try:
                    fill = self.broker.close_position(sym)
                except BadQuoteError:  # corrupt tick — hold the position, retry next cycle
                    logger.error("BAD-TICK GUARD: skipped %s exit this cycle (corrupt quote)", sym)
                    continue
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
                    try:
                        fill = self.broker.place_order(Order(symbol=sym, side=side, qty=half))
                    except BadQuoteError:  # corrupt tick — skip partial, retry next cycle
                        logger.error("BAD-TICK GUARD: skipped %s partial this cycle (corrupt quote)", sym)
                        continue
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

    def tradeable_now(self) -> list[str]:
        """Universe symbols whose market is currently open (NSE hours / forex / crypto)."""
        from .sessions import is_market_open
        return [s for s in settings.universe if is_market_open(s)]

    def sessions(self) -> dict:
        """Global market-session status + the current rotation focus."""
        from .sessions import session_status
        return session_status(settings.universe)

    def run_universe(self, execute: bool = True, interval: str | None = None,
                     open_only: bool = False) -> list[dict]:
        out = []
        interval = interval or settings.default_interval
        symbols = self.tradeable_now() if open_only else settings.universe
        if execute:
            try:
                self.manage_positions()
            except Exception:  # noqa: BLE001
                logger.exception("position management failed")
        for sym in symbols:
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
        if self.risk.marathon:  # run-to-ruin guard: stop honestly when capital is gone
            try:
                if self.broker.get_account().equity <= settings.starting_capital * 0.01:
                    self.risk.marathon = False
                    self.autonomous = False
                    self.bus.publish("control", {"event": "marathon_exhausted"})
                    self.notifier.send("Paper marathon ended", "Capital exhausted (equity ~0).", "critical")
            except Exception:  # noqa: BLE001
                pass
        self._save_broker_state()  # persist the book each cycle so positions survive a restart
        self._check_readiness_alert()
        self._cook_step()           # one cooking candidate per cycle — background discovery
        return out

    # --- continuous strategy cooking (background research) -------------
    def _cook_step(self) -> None:
        """Run one cooking round per cycle: pick a candidate not recently cooked,
        backtest + MC, persist verdict. Honest discovery — most rounds DROP."""
        try:
            from .cooking import CANDIDATES, cook_one, pick_next_candidate
            recent = [r["variant_id"] for r in self.repo.recent_cooking(len(CANDIDATES))]
            cand = pick_next_candidate(recent)
            if cand is None:
                return
            result = cook_one(self.provider, cand)
            self.repo.save_cooking_result(**result)
            logger.info("cook %s -> %s (avg %.2f%%, %d/%d MC robust)",
                        result["variant_id"], result["verdict"],
                        result["avg_return"] * 100, result["mc_robust_count"],
                        result["markets_tested"])
        except Exception:  # noqa: BLE001 - cooking must never break trading
            logger.exception("cooking step failed")

    def cooking_status(self) -> dict:
        """What's cooking right now — counts, recent rounds, leaderboard."""
        from .cooking import CANDIDATES
        recent = self.repo.recent_cooking(10)
        leaderboard = self.repo.cooking_leaderboard(8)
        counts = self.repo.cooking_counts()
        last_ts = recent[0]["ts"] if recent else None
        return {
            "candidates_total": len(CANDIDATES),
            "rounds_run": counts["total"],
            "verdicts": {"keep": counts["keep"], "review": counts["review"],
                         "drop": counts["drop"]},
            "last_round_ts": last_ts,
            "recent": recent,
            "leaderboard": leaderboard,
            "note": "Background research. Most rounds DROP — that's honest. KEEP / "
                    "REVIEW variants are candidates for promotion, never auto-deployed.",
        }

    def _check_readiness_alert(self) -> None:
        """Fire a one-shot alert the first time readiness gates flip to 6/6 — the
        empirical signal that micro-stage real money is permitted. Idempotent via
        a flag file so it's never repeated, even across restarts."""
        try:
            ds = self.deployment()
            r = ds.get("readiness") or {}
            if not (r.get("ready") and r.get("passed") == r.get("total")):
                return
            flag = Path(settings.data_cache_dir) / "readiness_alerted.flag"
            flag.parent.mkdir(parents=True, exist_ok=True)
            if flag.exists():
                return
            msg = (f"All {r['total']} go-live readiness gates have passed. Micro-stage real "
                   f"money is now mechanically permitted (₹2,000/trade cap). Review the "
                   f"forward record before arming AIFOS_LIVE_TRADING_ENABLED.")
            self.notifier.send("READY: 6/6 gates passed", msg, "critical")
            self.bus.publish("control", {"event": "readiness_ready",
                                          "passed": r["passed"], "total": r["total"]})
            flag.write_text(msg)
            logger.warning("READINESS ALERT: 6/6 gates passed — micro real money permitted")
        except Exception:  # noqa: BLE001 - alerting must never break the trading loop
            logger.exception("readiness alert check failed")

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

    def holdings(self) -> dict:
        """Open positions grouped by asset class — how much is invested in stocks,
        forex, crypto, etc. Options are always ₹0 (the system holds no options:
        there is no NSE options execution feed)."""
        from .data.models import classify_asset
        acct = self.broker.get_account()
        positions = [p.to_dict() for p in self.broker.get_positions()]
        buckets: dict[str, dict] = {}
        for p in positions:
            cls = classify_asset(p["symbol"]).value
            invested = round(abs(p["qty"]) * p["avg_price"], 2)
            p["asset_class"] = cls
            p["invested"] = invested
            b = buckets.setdefault(cls, {"invested": 0.0, "market_value": 0.0,
                                         "unrealized_pnl": 0.0, "count": 0})
            b["invested"] += invested
            b["market_value"] += abs(p["market_value"])
            b["unrealized_pnl"] += p["unrealized_pnl"]
            b["count"] += 1
        total = round(sum(b["invested"] for b in buckets.values()), 2)
        labels = {"equity": "Stocks", "forex": "Forex", "crypto": "Crypto",
                  "index": "Index", "options": "Options"}
        by_class = []
        for key in ("equity", "forex", "crypto", "index", "options"):
            b = buckets.get(key, {"invested": 0.0, "market_value": 0.0, "unrealized_pnl": 0.0, "count": 0})
            by_class.append({
                "key": key, "label": labels[key],
                "invested": round(b["invested"], 2), "market_value": round(b["market_value"], 2),
                "unrealized_pnl": round(b["unrealized_pnl"], 2), "count": b["count"],
                "pct": round(b["invested"] / total * 100, 1) if total else 0.0,
            })
        return {
            "mode": "live" if self.broker.is_live else "paper",
            "equity": round(acct.equity, 2), "cash": round(acct.cash, 2),
            "total_invested": total, "by_class": by_class,
            "positions": sorted(positions, key=lambda x: abs(x.get("market_value", 0.0)), reverse=True),
            "recent_trades": self.repo.recent_trades(10),
            "note": "Options = ₹0: the system trades stocks / forex / crypto only (no NSE options feed).",
        }

    # --- paper options lab (Black–Scholes model prices; learning sandbox) --
    def _underlying(self, symbol: str) -> tuple[float, float]:
        from .indicators import realized_vol
        df = self.provider.history(symbol, "1d")
        spot = float(df["close"].iloc[-1])
        rv = realized_vol(df["close"], 20).dropna()
        return spot, max(float(rv.iloc[-1]) if len(rv) else 0.20, 0.05)

    def option_strategies(self, symbol: str | None = None, days: int = 7) -> dict:
        from .options_lab import STRATEGIES, build_strategy, lot_size
        symbol = symbol or settings.default_symbol
        spot, vol = self._underlying(symbol)
        return {"symbol": symbol, "spot": round(spot, 2), "vol": round(vol, 3), "days": days,
                "lot_size": lot_size(symbol),
                "strategies": [build_strategy(n, symbol, spot, vol, days) for n in STRATEGIES]}

    def _mark_option(self, pos: dict) -> dict:
        from .options_lab import net_value
        spot = float(self.provider.history(pos["symbol"], "1d")["close"].iloc[-1])
        elapsed = (datetime.now(timezone.utc) - pos["opened_dt"]).total_seconds() / 86400.0
        remaining = max(0.0, pos["days_at_open"] - elapsed)
        cur = net_value(pos["legs"], spot, remaining / 365.0, pos["vol"])
        return {"id": pos["id"], "symbol": pos["symbol"], "strategy": pos["strategy"], "label": pos["label"],
                "legs": pos["legs"], "entry_spot": round(pos["entry_spot"], 2), "spot": round(spot, 2),
                "entry_net": pos["entry_net"], "current_value": cur, "pnl": round(cur - pos["entry_net"], 2),
                "days_left": round(remaining, 1), "max_profit": pos["max_profit"],
                "max_loss": pos["max_loss"], "breakevens": pos["breakevens"], "opened": pos["opened"]}

    def open_option_paper(self, symbol: str, strategy: str, days: int = 7, lots: int = 1) -> dict:
        from .options_lab import build_strategy, net_value
        spot, vol = self._underlying(symbol)
        s = build_strategy(strategy, symbol, spot, vol, days, lots)
        entry_net = net_value(s["legs"], spot, max(days, 1) / 365.0, vol)
        oid = self.repo.save_option(
            symbol=symbol, strategy=strategy, label=s["label"], legs=s["legs"],
            entry_spot=spot, entry_net=entry_net, days_at_open=days, vol=vol,
            meta={"max_profit": s["max_profit"], "max_loss": s["max_loss"], "breakevens": s["breakevens"]},
        )
        self.option_book[oid] = {
            "id": oid, "symbol": symbol, "strategy": strategy, "label": s["label"], "legs": s["legs"],
            "entry_spot": spot, "entry_net": entry_net,
            "opened": _now_iso(), "opened_dt": datetime.now(timezone.utc), "days_at_open": days, "vol": vol,
            "max_profit": s["max_profit"], "max_loss": s["max_loss"], "breakevens": s["breakevens"],
        }
        self.bus.publish("control", {"event": "option_open", "strategy": strategy, "symbol": symbol})
        return self._mark_option(self.option_book[oid])

    def option_positions(self) -> dict:
        return {"positions": [self._mark_option(p) for p in self.option_book.values()],
                "count": len(self.option_book)}

    def _load_options(self) -> None:
        """Restore open paper option positions from the DB (survive restarts)."""
        try:
            for r in self.repo.open_options():
                meta = r.get("meta") or {}
                self.option_book[r["id"]] = {
                    "id": r["id"], "symbol": r["symbol"], "strategy": r["strategy"],
                    "label": r["label"], "legs": r["legs"], "entry_spot": r["entry_spot"],
                    "entry_net": r["entry_net"], "opened": r["ts"],
                    "opened_dt": datetime.fromisoformat(r["ts"]).replace(tzinfo=timezone.utc),
                    "days_at_open": r["days_at_open"], "vol": r["vol"],
                    "max_profit": meta.get("max_profit"), "max_loss": meta.get("max_loss", 0.0),
                    "breakevens": meta.get("breakevens", []),
                }
        except Exception:  # noqa: BLE001 - a cold/missing table must not crash startup
            logger.exception("failed to load persisted option positions")

    def _load_broker_state(self) -> None:
        """Rehydrate the paper book (cash + open positions) across restarts."""
        if self.broker.is_live or not hasattr(self.broker, "restore"):
            return
        try:
            state = self.repo.load_broker_state()
            if state:
                self.broker.restore(state)
        except Exception:  # noqa: BLE001 - a cold/missing table must not crash startup
            logger.exception("failed to load persisted broker state")

    def _save_broker_state(self) -> None:
        """Persist the paper book so positions survive a restart/reboot."""
        if self.broker.is_live or not hasattr(self.broker, "snapshot"):
            return
        try:
            s = self.broker.snapshot()
            self.repo.save_broker_state(s["cash"], s["contributed"], s["realized_pnl"], s["positions"])
        except Exception:  # noqa: BLE001 - persistence must never break trading
            logger.exception("failed to save broker state")

    def _load_strategy_state(self) -> None:
        """Apply persisted enabled/disabled strategy flags on startup (MC enforcement sticks)."""
        try:
            from .strategies import set_enabled
            for name, enabled in self.repo.load_strategy_states().items():
                set_enabled(name, enabled)
        except Exception:  # noqa: BLE001 - cold/missing table must not crash startup
            logger.exception("failed to load persisted strategy state")

    def _persist_strategy_state(self) -> None:
        try:
            from .strategies import REGISTRY, is_enabled
            self.repo.save_strategy_states({n: is_enabled(n) for n in REGISTRY})
        except Exception:  # noqa: BLE001
            logger.exception("failed to persist strategy state")

    def close_option_paper(self, oid: int) -> dict:
        pos = self.option_book.get(int(oid))
        if not pos:
            return {"ok": False, "error": "no such paper option position"}
        final = self._mark_option(pos)
        self.repo.close_option(int(oid), final["pnl"])
        self.option_book.pop(int(oid), None)
        self.bus.publish("control", {"event": "option_close", "id": int(oid), "pnl": final["pnl"]})
        return {"ok": True, "closed": final}

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

    def strategy_market(self, symbol: str | None = None, interval: str | None = None) -> dict:
        """Backtest every registered strategy on a symbol, ranked by Sharpe — the
        'strategy marketplace'. Backtests are real history, NOT forward results."""
        from .backtest import monte_carlo, run_backtest
        from .strategies import REGISTRY, STRATEGY_INFO, build_strategy, is_enabled
        symbol = symbol or settings.default_symbol
        interval = interval or settings.default_interval
        df = self.provider.history(symbol, interval)
        df.attrs["symbol"] = symbol
        live = self.strategy_live_stats()
        rows: list[dict] = []
        for name in REGISTRY:
            row = {"name": name, "enabled": is_enabled(name), **STRATEGY_INFO.get(name, {}),
                   "live": live.get(name, {"trades": 0, "win_rate": 0.0, "realized_pnl": 0.0})}
            try:
                res = run_backtest(df, build_strategy(name), interval=interval,
                                   capital=settings.starting_capital)
                m = res.metrics
                row.update({"total_return": m["total_return"], "sharpe": m["sharpe"],
                            "sortino": m.get("sortino", 0.0), "max_drawdown": m["max_drawdown"],
                            "win_rate": m["win_rate"], "profit_factor": m["profit_factor"],
                            "num_trades": m["num_trades"]})
                mc = monte_carlo(res.trades)
                row["monte_carlo"] = {k: mc.get(k) for k in
                                      ("reliable", "verdict", "p_profit", "median_return",
                                       "return_without_best_trade")}
            except Exception as exc:  # noqa: BLE001
                row["error"] = str(exc)
            rows.append(row)
        # robustness-aware ranking: Sharpe, penalised for unreliable / fragile / unprofitable
        ranked = sorted([r for r in rows if "sharpe" in r], key=self._robustness_score, reverse=True)
        return {"symbol": symbol, "interval": interval, "strategies": rows,
                "best": ranked[0]["name"] if ranked else None,
                "note": "Backtested on real history, ranked by Monte-Carlo-adjusted robustness "
                        "(Sharpe penalised for fragile/unreliable edges). Backtests are not forward "
                        "results — the AI confirms a strategy by paper/forward-testing before trusting it."}

    @staticmethod
    def _robustness_score(r: dict) -> float:
        """Sharpe, penalised so a fragile or unprofitable edge ranks below a modest
        but robust one. Used to rank the marketplace and drive MC enforcement."""
        if "sharpe" not in r:
            return -99.0
        s = float(r.get("sharpe") or 0.0)
        tr = float(r.get("total_return") or 0.0)
        mc = r.get("monte_carlo") or {}
        if tr <= 0:
            s -= 1.0                                            # unprofitable on real history
        if mc.get("reliable") is False:
            s -= 0.4                                            # too few trades / no losses to test
        wob = mc.get("return_without_best_trade")
        if wob is not None and wob <= 0 < tr:
            s -= 0.6                                            # edge collapses without one trade
        return s

    def enforce_robustness(self, apply: bool = True) -> dict:
        """Monte Carlo ENFORCEMENT. Backtest each strategy across a multi-market
        basket, run MC, and AUTO-DISABLE any strategy that fails robustness on
        EVERY market it was tested on (unprofitable, or an edge that collapses
        without its single best trade). Honest: it can only DISABLE a fragile
        strategy, never enable one; survivors on any market are kept."""
        from .backtest import cost_stress, monte_carlo, run_backtest
        from .strategies import REGISTRY, build_strategy, is_enabled, set_enabled
        basket = ["^NSEI", "USDINR=X", "BTC-USD", "RELIANCE.NS"]
        disabled: list[dict] = []
        report: list[dict] = []
        for name in REGISTRY:
            results = []
            for sym in basket:
                try:
                    df = self.provider.history(sym, settings.default_interval)
                    df.attrs["symbol"] = sym
                    strat = build_strategy(name)
                    res = run_backtest(df, strat, interval=settings.default_interval,
                                       capital=settings.starting_capital)
                    mc = monte_carlo(res.trades)
                    cs = cost_stress(df, strat, interval=settings.default_interval,
                                     capital=settings.starting_capital)
                    tr = float(res.metrics["total_return"])
                    wob = mc.get("return_without_best_trade")
                    # robust = profitable AND not one-trade-dependent AND survives 2× costs
                    robust = (tr > 0
                              and not (wob is not None and wob <= 0 < tr)
                              and cs["survives_2x_cost"])
                    results.append({"symbol": sym, "total_return": round(tr, 4),
                                    "robust": robust, "cost_fragile": cs["cost_fragile"]})
                except Exception:  # noqa: BLE001
                    continue
            if not results:
                continue
            survives = any(r["robust"] for r in results)
            best = max(r["total_return"] for r in results)
            report.append({"strategy": name, "survives": survives, "best_return": best,
                           "markets": len(results),
                           "cost_fragile_markets": sum(1 for r in results if r["cost_fragile"])})
            if not survives and is_enabled(name):
                if apply:
                    set_enabled(name, False)
                disabled.append({"strategy": name,
                                 "reason": f"fails robustness on all {len(results)} markets "
                                           f"(best return {best:+.1%}; MC + 2×-cost stress)"})
        if apply and disabled:
            self._persist_strategy_state()  # MC enforcement now sticks across restarts
        return {"basket": basket, "applied": apply, "disabled": disabled, "report": report,
                "note": "Auto-disabled strategies that fail Monte Carlo robustness on EVERY tested "
                        "market. Re-enable manually in the marketplace if you disagree."}

    @staticmethod
    def _extraction_symbol(market) -> str:
        m = str(market or "").upper()
        if "BANK" in m:
            return "^NSEBANK"
        if "NIFTY" in m or "NSE" in m:
            return "^NSEI"
        return settings.default_symbol

    def ingest_extracted(self, payload: dict) -> dict:
        """Receive an LLM-extracted strategy (from n8n), store it for review, map it
        to the closest tested template, and backtest that template. No auto-deploy."""
        from .strategy_extraction import analyze_extraction
        a = analyze_extraction(payload)
        a["id"] = self.repo.save_extracted(
            source=a["source"], strategy_name=a["strategy_name"], payload=payload,
            mapped_template=a["mapped_template"], clarity=a["clarity"], status="review")
        try:
            from .backtest import run_backtest
            from .strategies import build_strategy
            sym = self._extraction_symbol(payload.get("market"))
            df = self.provider.history(sym, settings.default_interval)
            df.attrs["symbol"] = sym
            m = run_backtest(df, build_strategy(a["mapped_template"]),
                             interval=settings.default_interval, capital=settings.starting_capital).metrics
            a["backtest"] = {"symbol": sym, **{k: m[k] for k in
                             ("total_return", "sharpe", "max_drawdown", "win_rate", "num_trades")}}
        except Exception as exc:  # noqa: BLE001
            a["backtest"] = {"error": str(exc)}
        self.bus.publish("control", {"event": "strategy_extracted", "name": a["strategy_name"]})
        return {"ok": True, **a}

    def list_extracted(self) -> dict:
        return {"extracted": self.repo.list_extracted()}

    # --- video queue: the dashboard table n8n reads + writes back to -----
    def submit_video(self, url: str) -> dict:
        """A link pasted into the dashboard table — queue it for the n8n pipeline."""
        url = (url or "").strip()
        if not url:
            return {"ok": False, "error": "empty url"}
        vid = self.repo.save_video(url=url)
        self.bus.publish("control", {"event": "video_queued", "url": url})
        return {"ok": True, "id": vid, "url": url, "status": "queued"}

    def list_videos(self) -> dict:
        return {"videos": self.repo.list_videos()}

    def claim_videos(self, limit: int = 5) -> dict:
        """n8n polls this — atomically claims queued jobs (queued -> processing)."""
        return {"videos": self.repo.claim_queued_videos(int(limit))}

    def video_result(self, job_id: int, payload: dict) -> dict:
        """n8n writes the extracted strategy (or an error) back for a job. On success
        we ingest + backtest it and flip the row to done; otherwise mark it error."""
        job_id = int(job_id)
        err = payload.get("error") if isinstance(payload, dict) else None
        if err or not isinstance(payload, dict):
            self.repo.update_video(job_id, status="error", note=str(err or "bad payload")[:240])
            return {"ok": False, "job_id": job_id, "error": str(err or "bad payload")}
        res = self.ingest_extracted(payload)
        self.repo.update_video(
            job_id, status="done", extracted_id=int(res.get("id") or 0),
            title=str(res.get("strategy_name") or "")[:160],
            note=f"{res.get('mapped_template', '?')} · clarity {round((res.get('clarity') or 0) * 100)}%")
        return {"ok": True, "job_id": job_id, **res}

    def process_video(self, job_id: int) -> dict:
        """Process a queued link natively (no n8n): fetch transcript → extract a
        structured strategy → ingest (map to a tested template + backtest)."""
        from .video_pipeline import extract_strategy, fetch_title, fetch_transcript
        job_id = int(job_id)
        job = next((v for v in self.repo.list_videos(500) if v["id"] == job_id), None)
        if not job:
            return {"ok": False, "error": "job not found"}
        url = job["url"]
        self.repo.update_video(job_id, status="processing")
        title = fetch_title(url)
        transcript, err = fetch_transcript(url)
        if err:
            self.repo.update_video(job_id, status="error", title=title[:160], note=err[:240])
            return {"ok": False, "job_id": job_id, "error": err}
        try:
            payload, src = extract_strategy(transcript, title=title, url=url)
            res = self.ingest_extracted(payload)
        except Exception as exc:  # noqa: BLE001
            self.repo.update_video(job_id, status="error", title=title[:160], note=str(exc)[:240])
            return {"ok": False, "job_id": job_id, "error": str(exc)}
        self.repo.update_video(
            job_id, status="done", extracted_id=int(res.get("id") or 0),
            title=(payload.get("strategy_name") or title)[:160],
            note=f"{res.get('mapped_template', '?')} · clarity {round((res.get('clarity') or 0) * 100)}% · via {src}")
        return {"ok": True, "job_id": job_id, "source": src, **res}

    def process_queue(self, limit: int = 10) -> dict:
        """Drain queued links (used by the dashboard so it works without n8n)."""
        queued = [v for v in self.repo.list_videos(500) if v["status"] == "queued"][:int(limit)]
        out = []
        for j in queued:
            try:
                out.append(self.process_video(j["id"]))
            except Exception as exc:  # noqa: BLE001
                self.repo.update_video(j["id"], status="error", note=str(exc)[:240])
                out.append({"ok": False, "job_id": j["id"], "error": str(exc)})
        return {"processed": out, "count": len(out)}

    def pnl_breakdown(self) -> dict:
        """Booked P&L from CLOSED (realized) trades, split into profit booked vs
        loss booked — by market class (equity/forex/crypto/index/options) AND by
        the strategy that produced each trade. The paper-trading scoreboard."""
        from .data.models import classify_asset

        def bucket(d: dict, key: str) -> dict:
            return d.setdefault(key, {"profit": 0.0, "loss": 0.0, "trades": 0, "wins": 0})

        by_class: dict = {}
        by_strat: dict = {}
        for t in self.repo.recent_trades(2000):
            pnl = float(t.get("realized_pnl") or 0.0)
            if pnl == 0:  # opening legs carry no realized P&L; only count closes
                continue
            cls = classify_asset(t.get("symbol", "")).value
            strat = t.get("strategy") or "unattributed"
            for d, key in ((by_class, cls), (by_strat, strat)):
                b = bucket(d, key)
                b["trades"] += 1
                if pnl >= 0:
                    b["profit"] += pnl
                    b["wins"] += 1
                else:
                    b["loss"] += -pnl

        opt = self.repo.options_realized()  # the paper options lab
        if opt["trades"]:
            by_class["options"] = opt

        def finalize(d: dict) -> list[dict]:
            rows = [{"key": k, "profit": round(b["profit"], 2), "loss": round(b["loss"], 2),
                     "net": round(b["profit"] - b["loss"], 2), "trades": b["trades"],
                     "win_rate": round(b["wins"] / b["trades"], 3) if b["trades"] else 0.0}
                    for k, b in d.items()]
            return sorted(rows, key=lambda r: r["net"], reverse=True)

        classes, strategies = finalize(by_class), finalize(by_strat)
        profit = round(sum(r["profit"] for r in classes), 2)
        loss = round(sum(r["loss"] for r in classes), 2)
        acct = self.broker.get_account()
        return {
            "mode": "live" if self.broker.is_live else "paper",
            "account": {"equity": round(acct.equity, 2), "cash": round(acct.cash, 2),
                        "currency": acct.currency, "realized_pnl": round(acct.realized_pnl, 2)},
            "totals": {"profit_booked": profit, "loss_booked": loss,
                       "net_booked": round(profit - loss, 2),
                       "trades": sum(r["trades"] for r in classes)},
            "by_class": classes, "by_strategy": strategies,
        }

    def strategy_live_stats(self) -> dict:
        """Realized paper/live performance per strategy — the forward signal of what
        actually works, attributed by the strategy that opened each closed trade."""
        by: dict[str, dict] = {}
        for t in self.repo.recent_trades(3000):
            pnl = float(t.get("realized_pnl") or 0.0)
            if pnl == 0.0:
                continue  # only resolved (closing) trades carry P&L
            s = t.get("strategy") or "?"
            b = by.setdefault(s, {"trades": 0, "wins": 0, "pnl": 0.0})
            b["trades"] += 1
            b["wins"] += 1 if pnl > 0 else 0
            b["pnl"] += pnl
        return {s: {"trades": b["trades"],
                    "win_rate": round(b["wins"] / b["trades"], 3) if b["trades"] else 0.0,
                    "realized_pnl": round(b["pnl"], 2)} for s, b in by.items()}

    def toggle_strategy(self, name: str, on: bool) -> dict:
        from .strategies import REGISTRY, is_enabled, set_enabled
        if name not in REGISTRY:
            return {"ok": False, "error": f"unknown strategy '{name}'"}
        set_enabled(name, bool(on))
        self._persist_strategy_state()  # so manual toggles survive a restart
        return {"ok": True, "name": name, "enabled": is_enabled(name)}

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
            "candles": ctx.extra.get("candles", {}),
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

    def start_paper_marathon(self, *, light: bool = False) -> dict:
        """PAPER-only: run the autonomous loop CONTINUOUSLY with no daily-loss
        auto-stop, compounding realized P&L into position sizing, until stopped or
        capital is exhausted. Refuses on a live account (the kill switch is sacred
        for real money).

        light=True skips the marathon_status() quote fetch — used at BOOT so the
        FastAPI startup event never blocks on yfinance (a hung quote fetch there
        prevents uvicorn from serving at all)."""
        if self.broker.is_live:
            raise RuntimeError("marathon is paper-only; refusing on a LIVE account")
        self.risk.reset_kill_switch()
        self.risk.marathon = True
        self.autonomous = True
        self.bus.publish("control", {"event": "marathon", "on": True})
        self.notifier.send("Paper marathon started",
                           "Continuous paper trading — no daily-loss stop, profits compounded.", "info")
        if light:
            return {"marathon": True, "autonomous": True, "mode": "paper"}
        return self.marathon_status()

    def stop_paper_marathon(self) -> dict:
        self.risk.marathon = False
        self.autonomous = False
        self.bus.publish("control", {"event": "marathon", "on": False})
        return {"marathon": False, "autonomous": False, "mode": "paper"}

    def marathon_status(self) -> dict:
        acct = self.broker.get_account()
        start = settings.starting_capital or 1.0
        return {
            "marathon": self.risk.marathon,
            "autonomous": self.autonomous,
            "equity": round(acct.equity, 2),
            "starting_capital": round(start, 2),
            "pnl": round(acct.equity - start, 2),
            "capital_remaining_pct": round(max(0.0, acct.equity / start), 4),
            "mode": "live" if self.broker.is_live else "paper",
            "note": "Continuous paper trading, no daily-loss auto-stop; realized profit is "
                    "compounded into sizing. Stops on command or when capital is exhausted.",
        }

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
