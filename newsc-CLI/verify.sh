#!/usr/bin/env bash
# Smoke for unified newsc CLI (requires orchestrator up for API checks).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

pip install -q -e .

newsc --version
newsc --help >/dev/null

API="${NEWSC_API_URL:-http://127.0.0.1:8787}"
if ! curl -sf "$API/health" >/dev/null; then
  echo "[newsc-CLI verify] WARN: API not up at $API — skipping API smoke"
  exit 0
fi

OUT=$(newsc --format json health)
echo "$OUT" | python -c "import sys,json; d=json.load(sys.stdin); assert d.get('ok') is True, d"

newsc --format json vault status >/dev/null
newsc --format json sources list >/dev/null || true
newsc --format json digest today >/dev/null || true

echo "[newsc-CLI verify] PASS"
