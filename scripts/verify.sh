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
export PYTHONPATH="$ROOT:$ROOT/collectors/rss-CLI:$ROOT/collectors/youtube-CLI:$ROOT/collectors/bilibili-CLI:$ROOT/collectors/social-CLI:$ROOT/digest-CLI:$ROOT/newsc-CLI:${PYTHONPATH:-}"

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

echo "[verify] digest vault (sources → HTML)"
STAT=$(curl -sf "http://$ORCH_HOST:$ORCH_PORT/digests/vault/status")
echo "  $STAT"
echo "$STAT" | python -c "import sys,json; d=json.load(sys.stdin); assert d.get('readable') is True, d"
FILES=$(curl -sf "http://$ORCH_HOST:$ORCH_PORT/digests/vault/files?source=local-demo&limit=5")
echo "$FILES" | python -c "import sys,json; d=json.load(sys.stdin); assert d.get('count',0)>=1, d"
FILE=$(curl -sf "http://$ORCH_HOST:$ORCH_PORT/digests/vault/file?source=local-demo&path=demo.html")
echo "$FILE" | python -c "import sys,json; d=json.load(sys.stdin); assert 'Demo' in (d.get('html') or ''), d"

echo "[verify] subscribe sources CRUD"
SUB_WEB=$(curl -sf -X POST "http://$ORCH_HOST:$ORCH_PORT/sources" \
  -H 'Content-Type: application/json' \
  -d '{"name":"verify-web","type":"web","config":{"url":"https://example.com/verify"}}')
SUB_ID=$(echo "$SUB_WEB" | python -c "import sys,json; print(json.load(sys.stdin)['id'])")
curl -sf -X PATCH "http://$ORCH_HOST:$ORCH_PORT/sources/$SUB_ID" \
  -H 'Content-Type: application/json' \
  -d '{"name":"verify-web-2","config":{"url":"https://example.com/verify2"}}' >/dev/null
curl -sf -X PATCH "http://$ORCH_HOST:$ORCH_PORT/sources/$SUB_ID" \
  -H 'Content-Type: application/json' \
  -d '{"enabled":false}' >/dev/null
curl -sf -X DELETE "http://$ORCH_HOST:$ORCH_PORT/sources/$SUB_ID" >/dev/null
curl -sf -X POST "http://$ORCH_HOST:$ORCH_PORT/digests/vault/sources" \
  -H 'Content-Type: application/json' \
  -d '{"id":"verify-tmp","label":"verify","path":"daily","enabled":true}' >/dev/null
curl -sf -X DELETE "http://$ORCH_HOST:$ORCH_PORT/digests/vault/sources/verify-tmp" >/dev/null
echo "  subscribe CRUD ok"

echo "[verify] notes columns + quote"
COLS=$(curl -sf "http://$ORCH_HOST:$ORCH_PORT/note-columns")
echo "$COLS" | python -c "import sys,json; d=json.load(sys.stdin); assert d.get('count',0)>=1, d"
COL_ID=$(echo "$COLS" | python -c "import sys,json; print(json.load(sys.stdin)['columns'][0]['id'])")
NOTE=$(curl -sf -X POST "http://$ORCH_HOST:$ORCH_PORT/notes" \
  -H 'Content-Type: application/json' \
  -d "{\"column_id\":\"$COL_ID\",\"quote_text\":\"verify划选摘录\",\"source_kind\":\"digest\",\"source_title\":\"verify\"}")
NOTE_ID=$(echo "$NOTE" | python -c "import sys,json; d=json.load(sys.stdin); assert d.get('quote_text')=='verify划选摘录', d; print(d['id'])")
curl -sf -X DELETE "http://$ORCH_HOST:$ORCH_PORT/notes/$NOTE_ID" >/dev/null
echo "  notes ok"

echo "[verify] ask"
ASK=$(curl -sf -X POST "http://$ORCH_HOST:$ORCH_PORT/ai/ask" -H 'Content-Type: application/json' -d '{"question":"这条在说什么？"}')
echo "$ASK" | python -c "import sys,json; d=json.load(sys.stdin); assert d.get('answer'), d"

echo "[verify] newsc CLI smoke"
newsc --format json health | python -c "import sys,json; d=json.load(sys.stdin); assert d.get('ok') is True, d"
newsc --format json pipeline run rss >/dev/null
newsc --format json ai process --limit 5 >/dev/null
newsc --format json vault status | python -c "import sys,json; d=json.load(sys.stdin); assert 'readable' in d, d"
newsc --format json pipeline run sources >/dev/null || true
echo "  newsc CLI ok"

echo "[verify] ingest/batch"
INGEST_BATCH=$(curl -sf -X POST "http://$ORCH_HOST:$ORCH_PORT/ingest/batch" \
  -H 'Content-Type: application/json' \
  -d '{"items":[{"source":"rss","title":"cli-batch","content":"verify","url":"https://example.com/cli-batch-verify"}],"source_name":"verify-batch","enqueue_ai":false}')
echo "$INGEST_BATCH" | python -c "import sys,json; d=json.load(sys.stdin); assert 'run_id' in d, d"

# optional openclaw probe (non-fatal)
if [[ "${CHECK_OPENCLAW:-0}" == "1" ]]; then
  echo "[verify] openclaw probe (optional)"
  curl -sf "${OPENCLAW_GATEWAY_URL:-http://127.0.0.1:18789}/" >/dev/null && echo "  gateway ok" || echo "  gateway skip"
fi

echo "[verify] PASS"
