#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
REPO="$(cd "$ROOT/../.." && pwd)"
export PYTHONPATH="$REPO:$ROOT:${PYTHONPATH:-}"

newsc-bilibili --help >/dev/null
newsc-bilibili --local-db demo --format json | python -c "import sys,json; d=json.load(sys.stdin); assert 'run_id' in d, d"
echo "[bilibili-CLI verify] PASS"
