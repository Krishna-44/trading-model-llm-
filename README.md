# AIFOS — Artificial Intelligence Financial Operating System

A **local-first, probability-gated, multi-agent** autonomous trading research platform.
Not a "trading bot." AIFOS is an operating core whose **default behaviour is to do nothing**:
it studies markets, deliberates across a committee of agents, and only acts when a trade
clears a hard confidence + risk gate. Everything funnels through one kernel that can move
money — and, far more often, decides not to.

> **It does not promise profit.** It reasons in probabilities, minimises avoidable losses,
> and is engineered to *wait*. Live real-money trading is **OFF by default** behind an
> explicit gate. See [Safety & the live gate](#safety--the-live-gate).

![paper-first](https://img.shields.io/badge/mode-paper--first-22d3ee) ![python](https://img.shields.io/badge/python-3.11-3776AB) ![license](https://img.shields.io/badge/license-all%20rights%20reserved-555)

---

## What it does (today, running)

- **Real market data** — NSE equities + indices, **forex**, and crypto via `yfinance` (no API keys). Degrades to a synthetic series if offline so it always runs.
- **Multi-agent committee** — 8 agents (Market Analyst, Sentiment, News, Macro/Regime, Strategy Evolution, Risk Manager, Portfolio Optimizer, Compliance) deliberate into one decision with a combined confidence score and full reasoning trace.
- **Adaptive risk engine** — ATR-based stops/targets, fixed-fractional position sizing, R:R enforcement, exposure caps, a **daily-loss kill switch**, and a volatility kill (stand aside in chaos).
- **Backtesting** — vectorised, transaction costs + slippage, **no look-ahead**, plus **walk-forward** out-of-sample validation.
- **Paper execution** — a realistic paper broker (slippage, commission, correct long/short/averaging P&L) is the default venue.
- **Live-capable adapters** — Zerodha, Upstox, Angel One, OANDA — all behind the gate.
- **Self-evaluation + market memory** — a trade journal that mines honest lessons, and a dependency-free vector store of past market *situations* ("when it looked like this before, what happened?").
- **Futuristic dashboard** — TradingView-style candles, an AI confidence gauge, the live agent-reasoning panel, portfolio/risk dashboards, a streaming activity feed, and a kill switch — over REST + WebSocket.

---

## Quickstart

Requires **Python 3.11** (a 3.11 interpreter; `python3.11` recommended) and **Node 20+**.

```bash
cd ai-trading-os
./scripts/setup.sh          # backend venv + frontend deps

# terminal 1 — API on :8000
make backend

# terminal 2 — dashboard on :3000
make frontend
```

Open **http://localhost:3000**. No configuration needed — it runs in paper mode on real data.

### Alternative UI — AIFOS Vision

A second, fuller dashboard (TanStack Start + `lightweight-charts`) with a voice-driven **Vision** assistant lives in `vision-ui/`. It talks to the same backend:

```bash
# terminal 3 — Vision dashboard on :8080
make vision
```

Open **http://localhost:8080**. Configured via `vision-ui/.env` → `VITE_AIFOS_API=http://localhost:8000` (already set). Both UIs are interchangeable; pick whichever you prefer.

Sanity checks:

```bash
make smoke     # end-to-end: data -> committee -> risk -> paper trade -> backtest
make test      # 15 unit tests (indicators, backtest, risk, execution, committee)
```

### Full "production-shaped" stack (optional)

```bash
docker compose up --build   # Postgres/TimescaleDB + Redis + Ollama + API + UI
```

---

## How a decision is made

```
 market data ─► build context (price, ATR, volatility, exposure, liquidity)
            │
            ▼
   ┌────────────────────────── Agent Committee ──────────────────────────┐
   │ Strategy Evolution → picks best strategy for this symbol (backtested)│
   │ Market Analyst (primary vote) · Sentiment · News · Macro/Regime      │
   │ Risk Manager · Portfolio Optimizer · Compliance (veto powers)        │
   └──────────────────────────────────────────────────────────────────────┘
            │  weighted consensus  +  any veto?
            ▼
   Risk Engine: confidence ≥ threshold? size it, set ATR stop/target, R:R ≥ min,
                exposure within caps, kill switch clear?
            │
       ┌────┴─────┐
     approved   rejected ──► HOLD  (the common case)
       │
       ▼
   Executor → broker (PAPER by default; LIVE only if gate armed) → journal + memory
```

A `BUY`/`SELL` requires **consensus AND risk approval AND no veto AND confidence ≥ threshold**.
Anything less is a `HOLD`.

---

## Safety & the live gate

AIFOS is built **paper-first**. To ever route real orders, *all* of these must hold:

1. `AIFOS_LIVE_TRADING_ENABLED=true`
2. `AIFOS_BROKER=` a real broker (`zerodha|upstox|angelone|oanda`)
3. That broker's credentials present in the environment

If the gate is off, selecting a live broker **safely falls back to paper**. Per-trade caps,
a daily-loss kill switch, and a manual kill switch apply in every mode.

**Two honest constraints baked in:**

- **FEMA guard** — Indian residents generally cannot legally trade offshore spot FX (EURUSD, GBPUSD…). The compliance agent **vetoes** these unless `AIFOS_ALLOW_OFFSHORE_FOREX=true`. Use INR pairs / NSE currency derivatives instead.
- **Indian broker reality** — Kite Connect & co. are paid, need **daily token re-auth**, and have **no sandbox**, so "live" there means real money immediately. Validate on the free NSE-data paper path first.

> Managing **other people's** money autonomously is a regulated activity (SEBI/SEC). AIFOS is
> designed for a **single operator trading their own account**.

Configuration: copy `.env.example` → `.env`. Everything is optional; the live section is clearly marked.

---

## Layout

```
ai-trading-os/
├── backend/   FastAPI + the AIFOS kernel, agents, risk, backtest, execution, memory
│   └── aifos/{config,kernel,data,indicators,strategies,backtest,agents,risk,execution,persistence,memory,api}
├── frontend/  Next.js 14 + Tailwind dashboard (lightweight-charts, WebSocket)
├── docs / ARCHITECTURE.md   full system design + the 24-section blueprint + roadmaps
├── docker-compose.yml       Postgres/Timescale + Redis + Ollama + API + UI
└── scripts/   setup.sh · run-backend.sh · run-frontend.sh · smoke.py
```

See **[ARCHITECTURE.md](ARCHITECTURE.md)** for the full design, data model, RL/LLM plans, and the MVP → scale roadmap.

---

## Optional power-ups

- **Local LLM (Ollama) — free, no billing, runs on your machine.** AIFOS is
  **local-first**: the LLM priority is **Ollama → cloud (Anthropic/OpenAI/Gemini) →
  on-device keyword fallback**, so nothing breaks if no model is running. It powers the
  **Video → Strategy** extractor and Vision's open-ended answers.

  ```bash
  brew services start ollama     # persistent; or `ollama serve` for a foreground run
  ollama pull llama3             # or: mistral, phi3 (lightweight)   ·   ollama list
  ```
  Then in `backend/.env`:
  ```ini
  AIFOS_LLM_PROVIDER=ollama
  AIFOS_OLLAMA_MODEL=llama3       # must match a model you've pulled
  # AIFOS_OLLAMA_BASE_URL=http://localhost:11434   (default)
  ```
  Switch models by pulling another and changing `AIFOS_OLLAMA_MODEL`. Verify it's live:
  AIFOS logs `LLM ollama:<model> ok in N.Ns` per call, and the Video → Strategy row shows
  `via ollama` (vs `via keywords` when it fell back). Bare names (`OLLAMA_MODEL`) also work.
  Set `AIFOS_LLM_PROVIDER=anthropic|openai` (with a key) to use a hosted model instead.

  **Match the model to your GPU.** On a GPU with **< 8 GB** (e.g. an 8 GB Apple Silicon
  Mac, ~5 GB usable), prefer **`phi3`** (3.8B) — `llama3` 8B spills to CPU and is slow
  (extractions can exceed 3 min and time out → keyword fallback). With ≥ 12 GB, `llama3`
  or `mistral` give richer extractions. If a call times out, AIFOS logs it and falls back
  safely — it never hangs the request indefinitely.
- **ML/RL research stack** — `pip install -r backend/requirements-ml.txt` (PyTorch/SB3/Gymnasium) for the reinforcement-learning strategy search described in the architecture. Not required to run the platform.
- **24/7 paper-forward service (macOS launchd)** — run a separate paper-mode instance on
  `:8001` that trades the autonomous loop continuously and survives crashes/reboots, while
  your main `:8000` instance is untouched:
  ```bash
  scripts/paper-forward.sh install     # generate plists, load, start (autonomous armed at boot)
  scripts/paper-forward.sh status      # launchd state + health
  scripts/paper-forward.sh logs        # tail the rotated app log
  scripts/paper-forward.sh restart|stop|uninstall
  ```
  KeepAlive auto-restarts on crash; a 120s watchdog kickstarts it if it hangs; the app log
  rotates (5 MB × 5). Tune via the plist env (`AIFOS_CONFIDENCE_THRESHOLD`, etc.).
  **Note:** the closed-trade ledger + equity curve persist in `paper_forward.db`, but the
  paper broker holds **open positions in memory** — a restart resets the live book to the
  starting balance (in-flight trades are dropped, not closed). Position persistence across
  restarts is a separate hardening step.
