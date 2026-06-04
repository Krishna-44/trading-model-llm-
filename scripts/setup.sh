#!/usr/bin/env bash
# One-shot setup: backend venv (Python 3.11) + frontend deps.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "→ backend venv"
cd "$ROOT/backend"
if command -v python3.11 >/dev/null 2>&1; then PY=python3.11; else PY=python3; fi
[ -d .venv ] || "$PY" -m venv .venv
./.venv/bin/pip install -q --upgrade pip wheel
./.venv/bin/pip install -q -r requirements.txt

echo "→ frontend deps"
cd "$ROOT/frontend" && npm install

echo ""
echo "✓ setup complete."
echo "  Terminal 1:  make backend     # API on :8000"
echo "  Terminal 2:  make frontend    # dashboard on :3000"
echo "  Sanity:      make smoke && make test"
