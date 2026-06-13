# AIFOS on Raspberry Pi 5 — LIVE DEPLOYMENT STATUS (updated 2026-06-10)

⚠️ This supersedes the earlier version of this file. The earlier note said "the Pi
has never booted, hardware is the blocker" and assumed a systemd `aifos-paper`
deploy on :8001. **Both of those are now outdated.** The Pi IS booted and running
AIFOS live — but via the **Docker Compose stack on :8000**, not the systemd
marathon on :8001. Read this for the ACTUAL state.

────────────────────────────────────────────────────────────────────────
## TL;DR

- Pi 5 is up, headless, **static IP 192.168.60.183**, running AIFOS in Docker 24/7.
- AIFOS = the **Docker Compose "production-shaped" stack** (`~/aifos`): FastAPI
  backend **:8000**, Next.js frontend **:3000**, **postgres:16-alpine** :5432,
  redis :6379, ollama :11434. All `restart: unless-stopped` (self-heals on reboot).
- Mode = **paper** (₹10,00,000). **Live trading OFF** (`AIFOS_LIVE_TRADING_ENABLED=false`).
- Mac source (`~/ai-trading-os`) and the Pi deployment are **code-consistent** as of
  this date (same kernel + execution refactor + the new safety gates).
- The safety gates ARE wired and active on the Pi. The two new committee agents are
  deliberately OFF (see `backend/aifos/IMPROVEMENTS_WIRING.md` review verdict).

────────────────────────────────────────────────────────────────────────
## 1. ACCESS

- `ssh pi@192.168.60.183` — user `pi`, password `raspberry`, key auth on the Mac, NOPASSWD sudo.
  Host-key error fix: `ssh-keygen -R 192.168.60.183 -f /tmp/pi5_known_hosts` then `-o StrictHostKeyChecking=accept-new`.
- AIFOS dir on Pi: `~/aifos`. Boots from USB (black USB-2 port). IPv6 off. IP is STATIC.
- For a screen: VNC over WiFi (`192.168.60.183:5900`, wayvnc). **Do NOT attach an
  HDMI monitor** without the official 27W PSU — it brown-out-crashed the Pi (the
  marginal supply can't drive the monitor + 14 containers). Headless is stable.

────────────────────────────────────────────────────────────────────────
## 2. RUN MODE — important reconciliation

AIFOS has TWO run modes; know which is live:

- **(A) Docker Compose stack — THIS is what's deployed & running on the Pi.**
  `~/aifos/docker-compose.yml`. Backend :8000, postgres/redis/ollama. Durable DB.
- **(B) systemd "paper marathon" on :8001** (`scripts/aifos-paper.service`, SQLite,
  `make backend`). This is what the earlier note assumed — **it is NOT running on
  the Pi.** If you actually want (B) instead of (A), stop the compose stack and set
  up the systemd unit; don't run both (port/DB confusion).

Operate (A):
```
ssh pi@192.168.60.183
cd ~/aifos
sudo docker compose ps
sudo docker compose logs -f backend
sudo docker compose up -d                 # recover after reboot (also auto-restarts)
sudo docker compose up -d --build backend # after deploying code changes
```
Verify:
```
curl -s http://192.168.60.183:8000/api/portfolio        # paper acct, mode "paper"
curl -s -X POST http://192.168.60.183:8000/api/analyze -H 'content-type: application/json' -d '{"symbol":"^NSEI"}'
```

────────────────────────────────────────────────────────────────────────
## 3. DEPLOYMENT-SPECIFIC CHANGES (already in this repo's source)

1. **Risk gates WIRED into `kernel.py`** (`analyze()` → `_hard_gates()`), active:
   `risk/event_filter.py` (NSE expiry/RBI/auction no-trade windows),
   `risk/vol_gate.py` (panic/volatile/VIX hard stand-aside),
   `memory/brain_sync.py` (fire-and-forget decision→n8n-brain). 79 tests pass.
2. **`agents/multi_timeframe.py` + `agents/sector_rotation.py`** — tested but NOT
   registered in the committee (deliberate — see `backend/aifos/IMPROVEMENTS_WIRING.md`
   REVIEW VERDICT: redundancy + scope-mismatch). Don't enable without re-reading it.
3. **`indicators/extended.py`** — Ichimoku, Aroon, Hull MA, Volume Profile, anchored VWAP.
4. **`api/news_signal.py`** — `/api/news-signal` receiver (router not yet mounted in
   `app.py`; mount it to let the n8n news pipeline feed AIFOS).
5. **`notifications/telegram.py`** — alerts; no-op until `AIFOS_TELEGRAM_BOT_TOKEN`+`_CHAT_ID` set.
6. **`frontend/components/BacktestPanel.tsx`** + fixes (`ActivityFeed.tsx` removed a
   redundant `?? ""`; `next.config.js` has `eslint.ignoreDuringBuilds`) — needed so
   `next build` succeeds in the Docker image.
7. **docker-compose**: db = postgres:16-alpine (NOT TimescaleDB — see §5),
   `restart: unless-stopped` on all 5 services, `AIFOS_BRAIN_URL` env added.

📌 **Commit these to `main`.** The earlier note assumed "the Pi clones `main`, so it
gets everything for free." That's only true if these deployment changes are
committed. Verify with `git status` / `git diff` and commit before relying on a
fresh `git clone` reproducing the Pi.

Push Mac→Pi without git:
```
rsync -avz --exclude '.venv' --exclude 'node_modules' --exclude '.next' --exclude '.git' \
  -e "ssh -o UserKnownHostsFile=/tmp/pi5_known_hosts" \
  backend/ pi@192.168.60.183:/home/pi/aifos/backend/
ssh pi@192.168.60.183 'cd ~/aifos && sudo docker compose up -d --build backend'
```

────────────────────────────────────────────────────────────────────────
## 4. KNOWN GAPS / ACTION ITEMS

1. **Ollama model NOT pulled.** `AIFOS_OLLAMA_MODEL=llama3` but `ollama list` is
   empty → LLM layer falls back to the deterministic committee (11 agents still
   vote; logs show "LLM fallback: Ollama model 'llama3' not pulled"). To enable LLM:
   ```
   ssh pi@192.168.60.183 'cd ~/aifos && sudo docker compose exec ollama ollama pull llama3.2:3b'
   # set AIFOS_OLLAMA_MODEL: llama3.2:3b in docker-compose.yml, then: docker compose up -d backend
   ```
   ⚠ ~2GB + inference load — do after the 27W PSU, or use `AIFOS_LLM_PROVIDER=groq` + `GROQ_API_KEY` for fast cloud LLM instead.
2. **Brain ingestion 404s** until the n8n brain workflows are imported into the
   LOCAL n8n (owner account not created yet). Harmless; import to start memory flow.
3. **Live trading stays OFF** — real money only after the 6/6 readiness gates, ₹2,000 cap. Don't flip the gate programmatically.
4. **Broker API (Kite/AngelOne) not integrated** — paper on yfinance works without it.

────────────────────────────────────────────────────────────────────────
## 5. GOTCHAS (don't re-hit)

- **db = postgres:16-alpine, NOT TimescaleDB.** TimescaleDB's `timescaledb-tune`
  panics on Pi 5 cgroup (`/sys/fs/cgroup/memory.max` missing). AIFOS uses no
  hypertables, so plain Postgres is correct. Don't switch back on the Pi.
- **Frontend prod build is strict** (`next build` type-checks all). Run `tsc --noEmit`
  before deploying frontend; keep `eslint.ignoreDuringBuilds`.
- **All Pi services now auto-restart.** AIFOS originally lacked a restart policy and
  stayed dead after a power-crash; fixed (`restart: unless-stopped`).
- **Power is the real constraint.** Stable headless; get the official 27W Pi-5 PSU
  before attaching a monitor or pulling the Ollama model under load.

────────────────────────────────────────────────────────────────────────
## 6. NEIGHBOURS AIFOS CAN USE (same Pi)

- **JARVIS MCP** `http://192.168.60.183:8765/mcp` — 6 `aifos_*` tools call AIFOS's API (verified end-to-end).
- **Brain (n8n)** `http://192.168.60.183:5678` — AIFOS feeds it via `brain_sync` (once workflows imported).
- **Unified dashboard** `http://192.168.60.183:8080`. Also Grafana :3002, Prometheus :9090, Portainer :9000, Vaultwarden :8222, Chroma :8001, MinIO :9091, Uptime-Kuma :3001, Jupyter :8888. Restic backups + Tailscale installed.

────────────────────────────────────────────────────────────────────────
## 7. SECURITY (from prior chat — still applies)
- Rotate any AngelOne PIN / API key / Gemini / WiFi creds shared in chat.
- Change the Pi `pi` password from `raspberry`.
- Real money only at 6/6 readiness, ₹2,000 cap — never before.

## 8. ONE-LINER STATUS
```
ssh pi@192.168.60.183 'cd ~/aifos && sudo docker compose ps; curl -s localhost:8000/api/portfolio | head -c 160; echo; vcgencmd get_throttled; vcgencmd measure_temp'
```
Healthy = 5 services up, portfolio JSON `"mode":"paper"`, `throttled=0x0`.
