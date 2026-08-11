#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
REPO="$(cd "$ROOT/../.." && pwd)"
export PYTHONPATH="$REPO:$ROOT:${PYTHONPATH:-}"

newsc-social --help >/dev/null
newsc-social --local-db demo --format json | python -c "import sys,json; d=json.load(sys.stdin); assert 'run_id' in d, d"
echo "[social-CLI verify] PASS"
