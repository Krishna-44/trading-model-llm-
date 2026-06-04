#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../vision-ui"
[ -d node_modules ] || npm install
exec npm run dev
