#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
REPO="$(cd "$ROOT/../.." && pwd)"
export PYTHONPATH="$REPO:$ROOT:${PYTHONPATH:-}"

pip install -q -e "$REPO" 2>/dev/null || true

newsc-rss --help >/dev/null
# offline path
newsc-rss --local-db demo --format json | python -c "import sys,json; d=json.load(sys.stdin); assert 'run_id' in d, d"
echo "[rss-CLI verify] PASS"
