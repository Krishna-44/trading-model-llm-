"""AIFOS HTTP + WebSocket API.

All blocking work (market data, backtests, the agent committee) is dispatched to
a threadpool so the event loop stays responsive. The autonomous trading loop is
OFF by default and only runs in whatever mode the broker gate permits (paper
unless live is explicitly armed)."""
from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from ..backtest import run_backtest, walk_forward
from ..config import settings
from ..data.models import classify_asset
from ..kernel import get_kernel
from ..persistence.db import init_db
from ..strategies import REGISTRY, build_strategy

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("aifos.api")

app = FastAPI(title="AIFOS", version="0.1.0",
              description="Artificial Intelligence Financial Operating System")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    # dev convenience: accept the UI on any localhost port (lock down in prod)
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

AUTONOMOUS_INTERVAL_S = settings.autonomous_interval_s


# --- request models ------------------------------------------------------
class AnalyzeReq(BaseModel):
    symbol: str
    interval: str = settings.default_interval


class BacktestReq(BaseModel):
    symbol: str
    strategy: str = "momentum"
    interval: str = settings.default_interval
    params: dict = {}


class TickReq(BaseModel):
    symbol: str
    interval: str = settings.default_interval
    execute: bool = True


class CycleReq(BaseModel):
    execute: bool = True


class AutonomousReq(BaseModel):
    on: bool | None = None
    enabled: bool | None = None  # Lovable UI sends {enabled}; accept either


class ResetReq(BaseModel):
    confirm: bool = False  # must be true to wipe the paper track record


class VideoReq(BaseModel):
    url: str


class RLReq(BaseModel):
    symbol: str = settings.default_symbol
    steps: int = 12000  # longer default so the learned policy is meaningful


class AskReq(BaseModel):
    question: str


# --- lifecycle -----------------------------------------------------------
@app.on_event("startup")
async def _startup() -> None:
    init_db()
    k = get_kernel()  # warm the singleton + connect broker
    if not k.repo.equity_curve(1):
        k.snapshot_equity()  # seed an inception baseline so the curve starts at day one
    asyncio.create_task(_autonomous_loop())
    logger.info("AIFOS online | broker=%s live=%s llm=%s",
                settings.broker, settings.live_trading_enabled, settings.llm_provider)


async def _autonomous_loop() -> None:
    k = get_kernel()
    while True:
        await asyncio.sleep(AUTONOMOUS_INTERVAL_S)
        if not k.autonomous or k.risk.kill_switch_active:
            continue
        try:
            await run_in_threadpool(k.run_universe, True)
        except Exception:  # noqa: BLE001
            logger.exception("autonomous cycle error")


# --- meta ----------------------------------------------------------------
@app.get("/")
def root() -> dict:
    return {"name": "AIFOS", "version": app.version, "docs": "/docs",
            "philosophy": "Protect capital first. Default action is HOLD."}


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/config")
def config() -> dict:
    k = get_kernel()
    return {
        "universe": settings.universe,
        "default_symbol": settings.default_symbol,
        "default_interval": settings.default_interval,
        "base_currency": settings.base_currency,
        "broker": k.broker.name,
        "mode": "live" if k.broker.is_live else "paper",
        "live_trading_enabled": settings.live_trading_enabled,
        "allow_offshore_forex": settings.allow_offshore_forex,
        "llm": {"provider": settings.llm_provider, "available": k.committee.llm.available()},
        "strategies": list(REGISTRY),
        "risk_limits": k.risk.snapshot()["limits"],
    }


@app.get("/api/agents")
def agents() -> dict:
    return {"agents": get_kernel().committee.roster()}


# --- market --------------------------------------------------------------
@app.get("/api/market/universe")
def universe() -> dict:
    return {"universe": [{"symbol": s, "asset_class": classify_asset(s).value}
                         for s in settings.universe]}


@app.get("/api/market/candles")
async def candles(symbol: str, interval: str = settings.default_interval,
                  lookback: int = 240) -> dict:
    return await run_in_threadpool(get_kernel().candles, symbol, interval, lookback)


# --- intelligence --------------------------------------------------------
@app.post("/api/analyze")
async def analyze(req: AnalyzeReq) -> dict:
    decision, _ = await run_in_threadpool(get_kernel().analyze, req.symbol, req.interval, True)
    return decision.to_dict()


@app.post("/api/backtest")
async def backtest(req: BacktestReq) -> dict:
    def _run() -> dict:
        k = get_kernel()
        df = k.provider.history(req.symbol, req.interval)
        df.attrs["symbol"] = req.symbol
        strat = build_strategy(req.strategy, **req.params)
        res = run_backtest(df, strat, interval=req.interval, capital=settings.starting_capital)
        wf = walk_forward(df, strat, interval=req.interval)
        return {**res.to_payload(), "walk_forward": wf}
    return await run_in_threadpool(_run)


@app.get("/api/research/fundamentals")
async def fundamentals(symbol: str) -> dict:
    from ..research.fundamentals import get_fundamentals_client
    return await run_in_threadpool(lambda: get_fundamentals_client().get(symbol).to_dict())


@app.get("/api/analytics")
async def analytics(symbol: str = settings.default_symbol,
                    interval: str = settings.default_interval) -> dict:
    def _run() -> dict:
        from ..analytics import portfolio_analytics, strategy_comparison
        k = get_kernel()
        return {"live": portfolio_analytics(k.repo),
                "strategies": strategy_comparison(k.provider, symbol, interval)}
    return await run_in_threadpool(_run)


@app.get("/api/track-record")
async def track_record_ep() -> dict:
    """Honest forward paper performance since inception — prove it before real money."""
    return await run_in_threadpool(get_kernel().track_record)


@app.post("/api/track-record/reset")
async def track_record_reset_ep(req: ResetReq) -> dict:
    if not req.confirm:
        return {"ok": False,
                "error": 'send {"confirm": true} to wipe the paper track record and restart the clock'}
    summary = await run_in_threadpool(get_kernel().reset_track_record)
    return {"ok": True, **summary}


@app.get("/api/analytics/correlation")
async def correlation(interval: str = settings.default_interval) -> dict:
    from ..analytics import correlation_matrix
    return await run_in_threadpool(
        lambda: correlation_matrix(get_kernel().provider, settings.universe, interval))


@app.get("/api/market/heatmap")
async def heatmap(interval: str = settings.default_interval) -> dict:
    from ..analytics import market_heatmap
    return await run_in_threadpool(
        lambda: {"tiles": market_heatmap(get_kernel().provider, settings.universe, interval)})


@app.get("/api/alerts/status")
def alerts_status() -> dict:
    n = get_kernel().notifier
    return {"enabled": settings.alerts_enabled, "channels": n.channels()}


@app.post("/api/alerts/test")
def alerts_test() -> dict:
    return get_kernel().notifier.send("Test alert", "AIFOS alerts are wired and working.", "info")


@app.post("/api/learn/video")
async def learn_video(req: VideoReq) -> dict:
    from ..learning import learn_from_video

    def _run() -> dict:
        try:
            return learn_from_video(req.url)
        except Exception as exc:  # noqa: BLE001 - surface a clean error to the UI
            return {"error": str(exc)}
    return await run_in_threadpool(_run)


@app.get("/api/rl/status")
def rl_status_ep() -> dict:
    from ..rl import rl_status
    return rl_status()


@app.post("/api/rl/train")
async def rl_train(req: RLReq) -> dict:
    from ..rl import train
    return await run_in_threadpool(lambda: train(get_kernel().provider, req.symbol, req.steps))


@app.get("/api/execution/status")
async def execution_status() -> dict:
    import time as _t

    def _run() -> dict:
        k = get_kernel()
        b = k.broker
        t0 = _t.perf_counter()
        source, data_ok = "unknown", True
        try:
            source = k.provider.history(settings.default_symbol,
                                        settings.default_interval).attrs.get("source", "unknown")
        except Exception:  # noqa: BLE001
            data_ok = False
        data_ms = round((_t.perf_counter() - t0) * 1000, 1)
        t1 = _t.perf_counter()
        llm_ok = k.committee.llm.available()
        llm_ms = round((_t.perf_counter() - t1) * 1000, 1)
        return {
            "broker": {"name": b.name, "mode": "live" if b.is_live else "paper",
                       "connected": True, "live_gate": settings.live_trading_enabled},
            "data": {"provider": k.provider.name, "latency_ms": data_ms,
                     "source": source, "ok": data_ok},
            "llm": {"provider": settings.llm_provider, "available": llm_ok, "latency_ms": llm_ms},
            "costs": {"commission_bps": getattr(b, "commission_bps", 0.0),
                      "slippage_bps": getattr(b, "slippage_bps", 0.0)},
            "orders": {"total": len(k.repo.recent_trades(500)), "failed": 0, "queue": 0},
            "kill_switch": k.risk.kill_switch_active, "autonomous": k.autonomous,
        }
    return await run_in_threadpool(_run)


@app.get("/api/news")
async def news(symbol: str = settings.default_symbol) -> dict:
    from ..news import news_intelligence
    return await run_in_threadpool(lambda: news_intelligence(symbol))


@app.get("/api/news/ticker")
async def news_ticker_ep() -> dict:
    from ..news import market_news

    def _run() -> dict:
        mn = market_news()
        return {"items": [{"symbol": h.get("publisher", "MKT"), "title": h["title"],
                           "sentiment": h["sentiment"], "impact_score": h["impact_score"]}
                          for h in mn["headlines"]]}
    return await run_in_threadpool(_run)


@app.get("/api/news/similar")
async def news_similar(symbol: str, title: str) -> dict:
    from ..news import historical_similarity
    return await run_in_threadpool(lambda: historical_similarity(symbol, title))


@app.post("/api/assistant/ask")
async def assistant_ask(req: AskReq) -> dict:
    from ..assistant import answer
    return await run_in_threadpool(lambda: answer(get_kernel(), req.question))


@app.get("/api/assistant/info")
def assistant_info() -> dict:
    from ..assistant import engine_name
    return {"name": settings.assistant_name, "engine": engine_name()}


# --- execution / loop ----------------------------------------------------
@app.post("/api/tick")
async def tick(req: TickReq) -> dict:
    decision, fill = await run_in_threadpool(
        get_kernel().tick, req.symbol, req.interval, req.execute)
    return {"decision": decision.to_dict(), "fill": fill.to_dict() if fill else None}


@app.post("/api/cycle")
async def cycle(req: CycleReq) -> dict:
    results = await run_in_threadpool(get_kernel().run_universe, req.execute)
    return {"results": results}


# --- portfolio / risk / logs --------------------------------------------
@app.get("/api/portfolio")
async def portfolio() -> dict:
    return await run_in_threadpool(get_kernel().portfolio)


@app.get("/api/risk")
def risk() -> dict:
    return get_kernel().risk_snapshot()


@app.get("/api/decisions")
def decisions(limit: int = 50) -> dict:
    return {"decisions": get_kernel().repo.recent_decisions(limit)}


@app.get("/api/trades")
def trades(limit: int = 100) -> dict:
    return {"trades": get_kernel().repo.recent_trades(limit)}


@app.get("/api/journal")
def journal() -> dict:
    k = get_kernel()
    return {"lessons": k.evaluator.mine_lessons(), "entries": k.repo.recent_journal(50)}


# --- controls ------------------------------------------------------------
@app.post("/api/control/kill")
def kill(reason: str = "manual kill switch") -> dict:
    get_kernel().kill(reason)
    return {"ok": True, "kill_switch_active": True}


@app.post("/api/control/resume")
def resume() -> dict:
    get_kernel().resume()
    return {"ok": True, "kill_switch_active": False}


@app.post("/api/control/autonomous")
def autonomous(req: AutonomousReq) -> dict:
    k = get_kernel()
    flag = req.on if req.on is not None else bool(req.enabled)
    k.set_autonomous(flag)
    return {"ok": True, "autonomous": k.autonomous}


@app.post("/api/control/cycle")
async def control_cycle() -> dict:
    """Alias of /api/cycle (the Lovable UI calls this path)."""
    results = await run_in_threadpool(get_kernel().run_universe, True)
    return {"results": results}


# --- websocket -----------------------------------------------------------
@app.websocket("/api/ws")
async def ws(websocket: WebSocket) -> None:
    await websocket.accept()
    k = get_kernel()
    last_seq, _ = k.bus.since(0)
    try:
        snap = await run_in_threadpool(k.portfolio)
        await websocket.send_json({"kind": "snapshot", "portfolio": snap,
                                   "risk": k.risk_snapshot()})
        while True:
            last_seq, events = k.bus.since(last_seq)
            for e in events:
                await websocket.send_json(e)
            pf = await run_in_threadpool(k.portfolio)
            await websocket.send_json({"kind": "heartbeat", "portfolio": pf,
                                       "risk": k.risk_snapshot()})
            await asyncio.sleep(3)
    except WebSocketDisconnect:
        return
    except Exception:  # noqa: BLE001
        logger.exception("ws error")
        await websocket.close()
