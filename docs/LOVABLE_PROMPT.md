# AIFOS — Lovable build prompt

Paste the block below into Lovable. It builds a **frontend only** that connects to the
existing AIFOS FastAPI backend (REST + WebSocket). If Lovable struggles with the full
scope in one go, paste it in phases using the "BUILD ORDER" at the bottom.

---

You are building **AIFOS — Artificial Intelligence Financial Operating System**: a real-time,
futuristic, hedge-fund-grade dashboard for an autonomous, probability-gated AI trading platform.

This is a **FRONTEND ONLY**. Do NOT build trading logic, AI, or a backend. Consume an existing
FastAPI backend via REST + WebSocket. The base URL comes from an env var `VITE_AIFOS_API`
(default `http://localhost:8000`). CORS is already open for any localhost origin.

## Non-negotiable product rules (must be visible in the UI, never violated)
- NEVER imply guaranteed profit or zero loss. Show a persistent disclaimer: "AIFOS reasons in
  probabilities and does not guarantee profit. Paper-first; live execution is gated."
- The system's default action is **HOLD** — surface confidence and risk transparently.
- Clearly show **PAPER vs LIVE** mode. Live trading is gated and off by default.
- All metrics must be transparent/auditable — never fabricate numbers; if data is empty, say so.

## Tech stack
- React + Vite + TypeScript + TailwindCSS + shadcn/ui.
- Charts: **lightweight-charts** (TradingView) for candlesticks + volume; **recharts** for
  line/area/pie/bars. SVG for small gauges/heatmaps/correlation grids.
- **framer-motion** for subtle motion (panel mount, number transitions, ticker).
- Native **WebSocket** for real-time.
- All API calls go to `${VITE_AIFOS_API}` ; WebSocket to `${VITE_AIFOS_API.replace('http','ws')}/api/ws`.

## Design language (institutional, futuristic — Bloomberg × TradingView × Jarvis)
- Near-black background `#06070b` with subtle indigo/cyan radial glows; faint 32px engineering grid.
- **Glassmorphism** panels: translucent white/3%, backdrop-blur, 1px white/7% border, soft shadow,
  rounded-2xl.
- Accent **electric cyan** `#22d3ee` + indigo `#6366f1`. Long/up = emerald `#10b981`,
  short/down = rose `#f43f5e`, neutral = zinc.
- **Inter** for UI; **JetBrains Mono** (tabular-nums) for ALL numbers/tickers.
- Smooth transitions, micro-interactions, fully responsive, multi-monitor friendly. Dark mode
  default with an optional light mode toggle.

## Layout
A single-page command center, plus a floating voice assistant dock. Top→bottom:
**Header → Control bar → News ticker → Main grid → footer disclaimer → Assistant dock (fixed).**

### Header (full width, sticky)
Logo "AIFOS / Financial Operating System" + tagline "Protect capital first · default action is HOLD".
Status chips: streaming (green when WS connected), **PAPER/LIVE** badge, LLM on/off, an
**Autonomous** toggle, and a prominent red **Kill Switch** button (becomes "Resume" when halted).
Source: `GET /api/config`, `GET /api/risk`; controls: `POST /api/control/kill|resume|autonomous`.

### Control bar
Symbol `<select>` (from `GET /api/market/universe` → `[{symbol, asset_class}]`), the live price +
asset-class chip, and buttons: **Analyze**, **Backtest**, **Run Cycle (paper)**.

### News ticker (scrolling marquee, under control bar)
Continuous horizontal scroll of market headlines with a sentiment dot + source.
Source: `GET /api/news/ticker` → `{items:[{symbol, title, sentiment, impact_score}]}`.

### MAIN GRID

**1. TradingView chart panel** (large) — candlesticks + volume via lightweight-charts.
`GET /api/market/candles?symbol=&interval=1d&lookback=240` → `{source, candles:[{ts,open,high,low,close,volume}]}`.
Show a "live data" badge when `source==="yfinance"`.

**2. AI Confidence meter** — radial gauge 0–100% with a tick at the trade threshold (62%), the
action badge (BUY/SELL/HOLD), and sizing (entry/stop/target/R:R) when present.

**3. Decision Rationale** — the committee's plain-English verdict (action, side, why), data source.

**4. Agent Committee panel** — a "Desk Rationale" highlight box + a list of agents, each with
stance (bullish/bearish/neutral, color-coded), a confidence bar, a VETO badge, and reasoning.
2–4 + this all come from `POST /api/analyze {symbol,interval}` →
`{action, side, confidence, reasoning, llm_summary, source, sizing:{entry,stop_loss,take_profit,rr_ratio,size_value}, risk, opinions:[{agent,stance,confidence,weight,reasoning,veto}]}`.

**5. Fundamentals & Valuation** — company name/sector, a quality bar + value bar, a metric grid
(P/E, Fwd P/E, P/B, ROE, margin, rev growth, D/E, div yield, mkt cap), and a one-line read.
`GET /api/research/fundamentals?symbol=` → `{applicable, source, name, sector, metrics{...}, quality_score, value_score, stance, reasoning}`. Show "N/A for {symbol}" when not an equity.

**6. Market Heatmap** — tiles for the universe, colored by % change. `GET /api/market/heatmap` →
`{tiles:[{symbol, asset_class, price, change_pct}]}`.

**7. Correlation Matrix** — NxN colored grid (green positive, red negative).
`GET /api/analytics/correlation` → `{symbols, matrix}`.

**8. Allocation donut** — portfolio allocation by position market value, else 100% Cash (SVG donut).

**9. News Intelligence panel** — for the selected symbol: an aggregate sentiment chip, a scrollable
list of headlines (sentiment-colored left border, impact score, publisher, time, link), plus a
**"Historical Echoes"** sub-section: similar past events + their realized 5-day move ("—" if not
yet resolvable). `GET /api/news?symbol=` → `{count, headlines:[{title,publisher,link,ts,sentiment,impact_score}], aggregate:{sentiment,bullish,bearish,avg_impact}}`;
`GET /api/news/similar?symbol=&title=` → `{matches:[{symbol,title,similarity,forward_return_5d}], memory:{events}}`.

**10. Execution Engine panel** — status rows with green/red dots: broker (name·mode), live gate,
data feed + latency_ms + source, LLM, slippage/commission bps, orders/failed, autonomous.
`GET /api/execution/status`.

**11. Portfolio Overview** — big equity number, an equity-curve sparkline, cash/realized/unrealized,
open positions table (symbol, qty@avg, uPnL colored). `GET /api/portfolio` →
`{account:{cash,equity,currency,realized_pnl}, positions:[...], equity_curve:[{ts,equity,cash}], open_positions, unrealized_pnl, mode, broker}`.

**12. Adaptive Risk Engine** — daily-loss budget bar (% used), kill-switch state, and a limits grid
(confidence floor, max position %, max positions, min R:R, trades today, memory size).
`GET /api/risk` → `{kill_switch_active, kill_reason, daily_pnl, daily_loss_limit, daily_loss_used_pct, trades_today, autonomous, memory:{count}, limits:{confidence_threshold,max_position_pct,max_open_positions,max_daily_loss_pct,min_rr_ratio}}`.

**13. Live Activity feed** — streaming events (decisions/fills/control) with timestamps, fed by the
WebSocket. **14. Trade Log** — `GET /api/trades` → `{trades:[{ts,symbol,side,qty,price,realized_pnl,mode}]}`.

**15. AI Lab** (3 cards): **External Alerts** (channel status from `GET /api/alerts/status`, "Send
test" → `POST /api/alerts/test`); **Video Learning** (YouTube URL input → `POST /api/learn/video {url}`
→ show extracted `{strategy:{indicators,entry_rules,exit_rules,method}}`); **RL Strategy Search**
(`GET /api/rl/status`; "Train" → `POST /api/rl/train {symbol}` → show `{status, final_equity, buy_hold_equity}`).

**16. Performance Analytics** (full width) — left: live-account metrics grid (Sharpe, Sortino, Max DD,
profit factor, win rate, expectancy, daily/weekly/monthly P&L) with a "populates as trades close"
note when zero; right: a strategy-comparison table (return, Sharpe, max DD, win, PF) with a
"Past performance ≠ future results" disclaimer. `GET /api/analytics?symbol=` →
`{live:{...}, strategies:[{strategy,total_return,sharpe,max_drawdown,win_rate,profit_factor,num_trades}]}`.

### Assistant dock — "Vision" (fixed, bottom-right, collapsible)
A glassmorphism chat panel named from `GET /api/assistant/info` → `{name, engine}` (show the engine
chip, e.g. "local"). Chat history + input; sends `POST /api/assistant/ask {question}` →
`{answer, engine, symbol}` and renders the answer (preserve newlines).
**Voice (Web Speech API):**
- A mic button = one-shot speech-to-text → send.
- A wake-word toggle: continuously listen; when the transcript contains the assistant's name
  ("vision"), send the remainder as a question.
- Speak answers aloud via SpeechSynthesis.
- **Barge-in / interrupt:** while speaking, show a "⏹ Tap to stop speaking" button; ALSO cancel
  speech immediately when the user presses the mic or starts talking (recognition `onspeechstart`).
- Vision also **announces alerts out loud** from the WebSocket (kill-switch trips, resumes, fills):
  add a "🔔 …" message and speak it.
Vision can answer about the whole app and even control it (e.g. "stop trading", "what's happening
in the world") — the backend handles that; the dock just sends the text and renders/speaks the reply.

### Real-time (WebSocket `GET /api/ws`)
On connect you receive `{kind:"snapshot", portfolio, risk}`, then periodic
`{kind:"heartbeat", portfolio, risk}` (~every 3s) and event messages
`{kind:"decision"|"fill"|"control", seq, ts, ...}`. Use the heartbeat to keep Portfolio/Risk/Header
live, and push decision/fill/control into the Activity feed and the assistant's spoken alerts.
Auto-reconnect with backoff.

## Acceptance criteria
- Loads with zero config against `http://localhost:8000`; degrades gracefully if the backend is down
  (skeletons + "backend offline", never crash).
- Real candlesticks render; selecting a symbol updates chart + analysis + news + fundamentals + analytics.
- Confidence gauge, agent panel, risk, portfolio, news (with affected-stock tags), execution status,
  analytics, AI Lab, and the Vision dock all render with live data.
- Kill Switch + Autonomous toggles work and reflect WS state. Mode badge shows PAPER/LIVE correctly.
- The honesty disclaimer is always visible; no "guaranteed profit" language anywhere.
- Fully responsive; dark mode default; smooth, tasteful motion.

## BUILD ORDER (if doing it in phases)
1) Shell: header, control bar, config/universe wiring, dark theme, WebSocket + live Portfolio/Risk/Header.
2) Chart + Analyze flow: candles, confidence gauge, decision rationale, agent committee.
3) Market context: heatmap, correlation, allocation, news ticker + News Intelligence + Execution Engine.
4) Analytics + AI Lab + Trade Log + Activity feed.
5) Vision assistant dock with voice, alerts, and barge-in.
