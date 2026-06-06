#!/usr/bin/env bash
# AIFOS Raspberry Pi setup — clone, install deps, build venv, install service.
# Tested target: Raspberry Pi 4 (4GB+) or Pi 5, 64-bit Raspberry Pi OS / Ubuntu.
# Read it before running; honest about what works and what doesn't on a Pi.
#
# What works fine on a Pi:
#   - FastAPI + SQLite + the autonomous loop
#   - yfinance / RSS news / AngelOne SmartAPI (network only)
#   - The full paper marathon
#
# What WON'T work well (honest):
#   - Ollama llama3 / phi3 — Pi 4/5 has no GPU + tight RAM; the keyword fallback
#     is what'll actually run. Same as it does on our M3 anyway.
#   - PyTorch / RL (requirements-ml.txt) — finicky on arm64; skip unless needed.
#
# Storage: USE A USB SSD, NOT AN SD CARD. The autonomous loop writes SQLite every
# cycle; SD cards die in months under that load. Set the repo on the SSD.

set -euo pipefail
REPO="${REPO:-$HOME/ai-trading-os}"

echo "[1/6] system packages…"
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv python3.11-dev \
                        build-essential git curl logger \
                        libssl-dev libffi-dev libsqlite3-dev

echo "[2/6] clone repo to $REPO (skip if already present)…"
if [ ! -d "$REPO" ]; then
  echo "  -> please clone the repo to $REPO first, then re-run this script."
  echo "     example: git clone <your-url> $REPO"
  exit 1
fi

echo "[3/6] python venv + deps…"
cd "$REPO/backend"
python3.11 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt
# requirements-live.txt has AngelOne SDK; install only if you'll connect a broker
[ -f requirements-live.txt ] && ./.venv/bin/pip install -r requirements-live.txt || true

echo "[4/6] backend/.env — copy from .env.example, then EDIT IT BY HAND:"
[ ! -f .env ] && cp .env.example .env
echo "     -> $REPO/backend/.env"
echo "     Set AngelOne creds + AIFOS_LIVE_MONITOR_ONLY=true (keep monitor-only on Pi)."
echo "     NEVER commit this file."

echo "[5/6] install systemd units…"
sudo cp "$REPO/scripts/aifos-paper.service"           /etc/systemd/system/
sudo cp "$REPO/scripts/aifos-paper-watchdog.service"  /etc/systemd/system/
sudo cp "$REPO/scripts/aifos-paper-watchdog.timer"    /etc/systemd/system/
# Adjust the user in the unit if not 'pi'
WHOAMI=$(whoami)
if [ "$WHOAMI" != "pi" ]; then
  echo "   -> adjusting User=$WHOAMI in service unit"
  sudo sed -i "s|^User=pi|User=$WHOAMI|; s|^Group=pi|Group=$WHOAMI|; s|/home/pi/|$HOME/|g" \
      /etc/systemd/system/aifos-paper.service
fi
sudo systemctl daemon-reload

echo "[6/6] enable + start service + watchdog…"
sudo systemctl enable --now aifos-paper.service
sudo systemctl enable --now aifos-paper-watchdog.timer

echo
echo "DONE. Check it:"
echo "  systemctl status aifos-paper"
echo "  journalctl -u aifos-paper -f"
echo "  curl http://127.0.0.1:8001/api/health"
echo
echo "Dashboard (run on a machine that can reach the Pi):"
echo "  VITE_AIFOS_PAPER_API=http://<pi-ip>:8001 npm run dev   (from vision-ui/)"
