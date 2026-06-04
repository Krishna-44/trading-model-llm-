#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../backend"
[ -d .venv ] || { echo "run ./scripts/setup.sh first"; exit 1; }
exec env PYTHONPATH=. ./.venv/bin/uvicorn aifos.api.app:app \
  --host 0.0.0.0 --port "${AIFOS_API_PORT:-8000}" --reload
