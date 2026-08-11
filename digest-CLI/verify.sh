#!/usr/bin/env bash
# Offline-friendly smoke for newsc-digest CLI (requires orchestrator up).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

pip install -q -e .

newsc-digest --version
newsc-digest --help >/dev/null

API="${NEWSC_API_URL:-http://127.0.0.1:8787}"
if ! curl -sf "$API/health" >/dev/null; then
  echo "[digest-CLI verify] WARN: API not up at $API — skipping push smoke"
  exit 0
fi

newsc-digest vault status --format json >/dev/null
OUT=$(newsc-digest push --demo --format json)
echo "$OUT" | python -c "import sys,json; d=json.load(sys.stdin); assert d.get('ok') is True, d; assert d.get('bytes',0)>0, d"
echo "[digest-CLI verify] PASS"
