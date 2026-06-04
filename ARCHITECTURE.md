# AIFOS — Architecture & Blueprint

**Legend:** ✅ built & verified · 🟡 scaffolded / seed (real, extend later) · ⬜ planned (designed, not yet coded)

This document is the north star. The repo today is a **runnable vertical slice** of it: the full
decision loop works on real data, paper-first, with the live path gated. Sections below mark exactly
what is implemented versus designed-for-later, honestly.

---

## 1. System Architecture

```
                         ┌──────────────────────────────────────────┐
                         │            Next.js Dashboard (UI)          │  ✅
                         │  charts · confidence · agents · risk · WS  │
                         └───────────────┬──────────────┬────────────┘
                                REST      │              │  WebSocket
                         ┌───────────────▼──────────────▼────────────┐
                         │              FastAPI API layer              │  ✅
                         └───────────────────────┬────────────────────┘
                                                 │
                         ┌───────────────────────▼────────────────────┐
                         │                 AIFOS Kernel                 │  ✅
                         │   build_context → deliberate → risk-gate →   │
                         │        execute → persist → learn             │
                         └──┬─────────┬─────────┬─────────┬─────────┬───┘
                            │         │         │         │         │
                    ┌───────▼──┐ ┌────▼───┐ ┌───▼────┐ ┌──▼─────┐ ┌─▼────────┐
                    │  Data    │ │ Agent  │ │ Risk   │ │ Broker │ │ Memory / │
                    │ providers│ │committee│ │ engine │ │ adapters│ │ journal  │
                    │  ✅      │ │  ✅    │ │  ✅    │ │ ✅/🟡  │ │   🟡     │
                    └────┬─────┘ └───┬────┘ └────────┘ └───┬────┘ └────┬─────┘
                         │           │ LLM (Ollama/api) 🟡 │           │
                    yfinance     deterministic quant    paper/live   SQLite/PG
                    (live data)   + optional LLM         execution   + vectors
```

**Microservice decomposition (target):** the kernel's sub-systems (data, agents, risk, execution,
learning) are already clean module boundaries. They split into independent services behind Redis
Streams / Kafka without rewrites — see §22.

## 2. System Design Diagrams
- **Decision flow** — see README "How a decision is made". ✅
- **Event flow (live):** kernel `EventBus` → WebSocket → UI. ✅ (in-process ring buffer; ⬜ Redis pub/sub for multi-node)
- **Learning loop:** trade → journal (predicted vs actual) → lesson mining + market-memory vectors → informs future confidence. 🟡

## 3. Folder Structure
See README "Layout". Backend is a single installable package `aifos/` with one module per concern;
frontend is Next.js App Router with `components/` + `lib/`. ✅

## 4. Database Schema  ✅ (SQLite default; Postgres/Timescale drop-in)
```
decisions(id, ts, symbol, action, confidence, executed, reasoning,
          agent_opinions JSON, risk JSON)
trades(id, ts, symbol, side, qty, price, commission, realized_pnl, order_id, mode)
equity_curve(id, ts, equity, cash)
journal(id, ts, symbol, decision_id, predicted JSON, actual JSON, outcome, lesson)
```
⬜ **TimescaleDB hypertables** for `market_bars` (OHLCV) + `equity_curve`; ⬜ pgvector for embeddings
(today market-memory vectors are a local pickle store — same interface, swappable).

## 5. API Architecture  ✅
REST: `/api/config · /market/universe · /market/candles · /analyze · /backtest · /tick · /cycle ·
/portfolio · /risk · /agents · /decisions · /trades · /journal · /control/{kill,resume,autonomous}`.
WebSocket `/api/ws`: snapshot + event stream + 3s portfolio/risk heartbeat. OpenAPI at `/docs`.

## 6. AI Training Pipeline
- ✅ **Backtest + walk-forward** harness is the evaluation substrate.
- ✅ **Strategy Evolution agent** selects the best strategy per symbol by risk-adjusted backtest (meta-selection — the seed of optimisation).
- 🟡 **Self-evaluation**: predicted-vs-actual journaling + lesson mining.
- ⬜ **RL training** (below), ⬜ **online learning** updating agent weights from realised outcomes, ⬜ **LLM fine-tuning** on the trade journal.

## 7. Reinforcement Learning Flow  ⬜ (designed; `requirements-ml.txt` ready)
```
Gymnasium env: state = [returns, RSI, ATR, vol-regime, position, drawdown, exposure]
               action = {flat, long, short} × size bucket
               reward = Δequityₜ − λ·drawdownₜ − cost   (risk-adjusted, penalises DD)
Algo: PPO / DQN via Stable-Baselines3 → train on historical + simulated regimes
      (bull/bear/sideways/crash) → policy proposes; RISK ENGINE still gates every action.
```
RL **never** bypasses the risk engine — it proposes, the engine disposes.

## 8. Broker Integration Architecture  ✅ interface · ✅ paper · 🟡 live
One `BrokerAdapter` ABC (`connect/get_account/get_positions/get_price/place_order/close_position`).
`PaperBroker` ✅ full sim. Live adapters — `AngelOneBroker` ✅ real SmartAPI (TOTP login +
scrip-master token resolution, NSE equity); `OANDABroker` real v20 REST; `ZerodhaBroker` Kite SDK;
`Upstox` gated stub — all enforce: gate ON + credentials present, else `LiveTradingDisabled`.
Registry falls back to paper when the gate is closed. FEMA guard on offshore FX.

## 9. LLM Integration Plan  🟡
Provider-abstracted `LLMClient` (Ollama local ✅, Anthropic/OpenAI ✅ via key). Used to synthesise the
**desk rationale** from structured agent opinions — **augmentation only**; the trading math is fully
deterministic and runs with the LLM absent. ⬜ Next: LLM-classified news/event extraction, retrieval
over the journal (RAG), and explanation grounding.

## 10. Security Architecture  🟡
- ✅ Secrets via env (`.env`, never committed); credentials only read when the matching live broker is armed.
- ✅ Live gate + per-trade caps + kill switches; compliance veto agent.
- ⬜ API auth (API keys/JWT), RBAC, MFA, rate limiting, audit-log table, anomaly detection, isolated execution sandbox. (Patterns mirror the user's `ai-governance-os` stack and port directly.)

## 11. Frontend UI Structure  ✅
Next.js 14 + Tailwind + lightweight-charts. Components: `Header` (mode/kill/autonomous), `Chart`,
`ConfidenceMeter`, `AgentPanel` (+ desk rationale), `RiskDashboard`, `PortfolioOverview`,
`ActivityFeed`, `TradeLog`. Live via `useAifosSocket`. Dark, responsive.

## 12. Backend Services  ✅
FastAPI + the kernel singleton; blocking work (data, backtests, committee) dispatched to a threadpool.
Autonomous background loop (OFF by default) ticks the universe on an interval, respecting the gate.

## 13. Docker Setup  ✅
`backend/Dockerfile` (py3.11 + psycopg), `frontend/Dockerfile` (Next build), `docker-compose.yml`
(Timescale + Redis + Ollama + API + UI).

## 14. Kubernetes Setup  ⬜
Target: Deployments for `api`, `worker` (autonomous loop), `ui`; StatefulSets for Postgres/Redis;
HPA on the worker; secrets via Vault/Sealed-Secrets. Compose is the on-ramp; manifests are a port.

## 15. CI/CD  ⬜ (designed)
GitHub Actions: `pytest` + `next build` + `ruff`/`tsc` on PR; image build/push on tag; `compose`-based
smoke in CI. `make test` is already the gate.

## 16–18. Roadmap (Dev / MVP / Scale)
- **MVP (this repo)** ✅ — real data, committee, risk gate, paper execution, backtests, dashboard, kill switch.
- **Phase 2** 🟡→⬜ — durable Timescale/pgvector; news/sentiment via real feeds + LLM; richer self-eval; auth/RBAC/audit; one live broker end-to-end on a tiny capped account.
- **Phase 3** ⬜ — RL strategy search; online learning of agent weights; multi-account; options/derivatives; the video/"Trader Knowledge Ingestion" pipeline (transcribe → chart CV → strategy extraction → backtestable rules).
- **Scale** ⬜ — split kernel sub-systems into services over Kafka; K8s + HPA; multi-region data; GPU training nodes.

## 19. Cost Optimization
Local-first by default = ₹0 infra to run. Local LLM (Ollama) avoids per-token cost. yfinance data is
free; paid feeds only when needed. GPU is rented per training job, not always-on. SQLite → Postgres only
when durability/concurrency demands it.

## 20. GPU Infrastructure
Dev: **Apple M3 / MPS** (this machine) for inference + light training. Heavy RL/forecasting training:
rent a single NVIDIA A10/A100 hourly; AIFOS inference (committee + small models) runs CPU/MPS fine.

## 21. Open-Source Models / Libraries
Running: `pandas/numpy`, `yfinance`, `FastAPI`, `SQLAlchemy`, `lightweight-charts`, `Ollama` (Llama 3.1).
Planned: `PyTorch`, `Stable-Baselines3`, `Gymnasium`, and study/reuse from `OpenBB`, `FinRL`, `Qlib`,
`Backtrader/Zipline`, `CCXT`, `Prophet`. (The bundled backtester is intentionally dependency-light;
swap in Backtrader/vectorbt where richer features help.)

## 22. Autonomous Agent Communication
Today: in-process committee — synchronous deliberation, weighted-consensus + veto, one `TradeDecision`. ✅
Target: agents as services exchanging typed messages over Redis Streams/Kafka; the committee becomes a
coordinator topic; opinions, vetoes and fills are events. The dataclasses (`AgentOpinion`, `TradeDecision`)
are already the wire schema. 🟡→⬜

## 23. Monitoring Stack
✅ structured logs + the in-app risk/activity telemetry. ⬜ Prometheus metrics (decisions, fills, latency,
drawdown), OTLP traces, Grafana dashboards, anomaly alerts — same self-hosted pattern as `ai-governance-os`.

## 24. Production Deployment Guide
1. `cp .env.example .env`; set `DATABASE_URL` (Timescale), secrets. 2. `docker compose up --build`.
3. Validate in paper for a meaningful window; watch the journal + walk-forward. 4. To go live: install
`requirements-live.txt`, set broker creds, flip `AIFOS_LIVE_TRADING_ENABLED=true` with **small caps**,
keep the kill switch reachable. 5. Add monitoring/auth before exposing beyond localhost.

## 25. Research Layer — OpenBB (🟡 additive, optional)
`research/fundamentals.py` is an OpenBB-style, provider-abstracted fundamentals service: quality +
value scoring → a stance. Free via yfinance today; uses the `openbb` SDK if installed
(`requirements-research.txt`, separate venv). Powers the **Fundamentals agent** (votes on equities,
abstains weight-0 elsewhere so the core is unchanged), the `/api/research/fundamentals` endpoint, and
the dashboard Research panel. OpenBB is cloned to `.external/` for study only — not a runtime dep.

---

## The AIFOS OS mapping
| OS concept (your spec) | Where it lives |
|---|---|
| Autonomous Learning Kernel | `kernel.py` ✅ |
| Financial Intelligence Engine | `agents/` committee ✅ |
| Multi-Agent Coordination | `agents/committee.py` ✅ |
| Reinforcement Learning Core | `requirements-ml.txt` + §7 ⬜ |
| Strategy Evolution System | `agents/governance.py:StrategyEvolutionAgent` 🟡 |
| Market Memory DB | `memory/vector.py` 🟡 |
| Self-Evaluation Engine | `memory/journal.py` 🟡 |
| Adaptive Risk Engine | `risk/engine.py` ✅ |
| Real-Time Decision Layer | `api` + WebSocket + kernel ✅ |
| Cross-Platform Trading Controller | `execution/` adapters ✅/🟡 |

## Core philosophy (enforced in code)
1. **Protect capital first** — every order passes risk + compliance; default is HOLD.
2. **Reason in probabilities** — confidence is explicit and gated; **no profit guarantees, ever**.
3. **Wait by default** — no edge ⇒ hold cash. 4. **Learn** — journal predicted-vs-actual, mine lessons.
5. **Real money is sacred** — live is OFF until consciously armed, with caps and kill switches.
