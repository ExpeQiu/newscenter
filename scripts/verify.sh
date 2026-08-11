#!/usr/bin/env bash
# Verify NewsC Mock-first loop.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  cp .env.example .env
fi
# shellcheck disable=SC1091
set -a
source .env
set +a

export AI_MOCK_MODE=true
export AI_PROVIDER=mock
export PYTHONPATH="$ROOT:$ROOT/collectors/rss-CLI:$ROOT/collectors/youtube-CLI:$ROOT/collectors/bilibili-CLI:${PYTHONPATH:-}"

# shellcheck disable=SC1091
source .venv/bin/activate 2>/dev/null || {
  python3 -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install -q -U pip
  pip install -q -e .
}

echo "[verify] provider factory"
python - <<'PY'
from intelligence.factory import create_provider
p = create_provider()
assert p.name == "mock", p.name
print("  create_provider ->", p.name)
PY

echo "[verify] content_hash stability"
python - <<'PY'
from pipeline.normalize import CollectItem, content_hash
a = CollectItem(source="rss", title="T", content="C", url="http://x")
b = CollectItem(source="rss", title="T", content="C", url="http://x")
assert content_hash(a) == content_hash(b)
print("  hash ok", content_hash(a)[:12])
PY

ORCH_HOST="${ORCH_HOST:-127.0.0.1}"
ORCH_PORT="${ORCH_PORT:-8787}"

# ensure API up
if ! curl -sf "http://$ORCH_HOST:$ORCH_PORT/health" >/dev/null; then
  echo "[verify] starting api only"
  ./scripts/start.sh api
fi

echo "[verify] health"
HEALTH=$(curl -sf "http://$ORCH_HOST:$ORCH_PORT/health")
echo "  $HEALTH"
echo "$HEALTH" | grep -q '"ok":true\|"ok": true'

echo "[verify] demo ingest (rss)"
INGEST=$(curl -sf -X POST "http://$ORCH_HOST:$ORCH_PORT/pipelines/rss/run")
echo "  $INGEST"

echo "[verify] demo ingest duplicate -> skip"
INGEST2=$(curl -sf -X POST "http://$ORCH_HOST:$ORCH_PORT/pipelines/rss/run")
echo "  $INGEST2"
echo "$INGEST2" | python -c "import sys,json; d=json.load(sys.stdin); assert d.get('inserted',0)==0, d"

echo "[verify] youtube + bilibili demo"
curl -sf -X POST "http://$ORCH_HOST:$ORCH_PORT/pipelines/youtube/run" >/dev/null
curl -sf -X POST "http://$ORCH_HOST:$ORCH_PORT/pipelines/bilibili/run" >/dev/null

echo "[verify] ai jobs process (mock)"
PROC=$(curl -sf -X POST "http://$ORCH_HOST:$ORCH_PORT/ai/jobs/process" -H 'Content-Type: application/json' -d '{"limit":50,"include_digest":true}')
echo "  processed=$(echo "$PROC" | python -c "import sys,json; print(json.load(sys.stdin).get('processed'))")"

echo "[verify] items have summaries"
ITEMS=$(curl -sf "http://$ORCH_HOST:$ORCH_PORT/items?limit=5")
echo "$ITEMS" | python -c "import sys,json; d=json.load(sys.stdin); assert d['count']>0; assert any(i.get('summary') for i in d['items']), d"

echo "[verify] digest today"
DIG=$(curl -sf "http://$ORCH_HOST:$ORCH_PORT/digests/today")
echo "$DIG" | python -c "import sys,json; d=json.load(sys.stdin); assert d.get('markdown'), d"

echo "[verify] ask"
ASK=$(curl -sf -X POST "http://$ORCH_HOST:$ORCH_PORT/ai/ask" -H 'Content-Type: application/json' -d '{"question":"这条在说什么？"}')
echo "$ASK" | python -c "import sys,json; d=json.load(sys.stdin); assert d.get('answer'), d"

# optional openclaw probe (non-fatal)
if [[ "${CHECK_OPENCLAW:-0}" == "1" ]]; then
  echo "[verify] openclaw probe (optional)"
  curl -sf "${OPENCLAW_GATEWAY_URL:-http://127.0.0.1:18789}/" >/dev/null && echo "  gateway ok" || echo "  gateway skip"
fi

echo "[verify] PASS"
