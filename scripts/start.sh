#!/usr/bin/env bash
# Start NewsC orchestrator (+ optional web).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p pids logs

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "[start] created .env from .env.example"
fi

# shellcheck disable=SC1091
set -a
source .env
set +a

export PYTHONPATH="$ROOT:$ROOT/collectors/rss-CLI:$ROOT/collectors/youtube-CLI:$ROOT/collectors/bilibili-CLI:${PYTHONPATH:-}"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install -q -U pip
  pip install -q -e .
else
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

# migrate / create tables
python - <<'PY'
from pipeline.db import init_db
init_db()
print("[start] db schema ready")
PY

ORCH_PORT="${ORCH_PORT:-8787}"
ORCH_HOST="${ORCH_HOST:-127.0.0.1}"
WEB_PORT="${WEB_PORT:-3000}"

if [[ -f pids/orchestrator.pid ]] && kill -0 "$(cat pids/orchestrator.pid)" 2>/dev/null; then
  echo "[start] orchestrator already running pid=$(cat pids/orchestrator.pid)"
else
  nohup uvicorn orchestrator.main:app --host "$ORCH_HOST" --port "$ORCH_PORT" \
    > logs/orchestrator.log 2>&1 &
  echo $! > pids/orchestrator.pid
  echo "[start] orchestrator pid=$(cat pids/orchestrator.pid) :$ORCH_PORT"
fi

# wait health
for i in $(seq 1 30); do
  if curl -sf "http://$ORCH_HOST:$ORCH_PORT/health" >/dev/null; then
    echo "[start] health ok"
    break
  fi
  sleep 0.3
  if [[ $i -eq 30 ]]; then
    echo "[start] health timeout" >&2
    exit 1
  fi
done

MODE="${1:-all}"
if [[ "$MODE" == "api" ]]; then
  exit 0
fi

if [[ -d apps/web ]]; then
  NPM_CACHE="$ROOT/.npm-cache"
  if [[ ! -d apps/web/node_modules ]]; then
    (cd apps/web && npm install --cache "$NPM_CACHE")
  fi
  if [[ -f pids/web.pid ]] && kill -0 "$(cat pids/web.pid)" 2>/dev/null; then
    echo "[start] web already running pid=$(cat pids/web.pid)"
  else
    cd apps/web
    nohup npm run dev -- -p "$WEB_PORT" > ../../logs/web.log 2>&1 &
    echo $! > ../../pids/web.pid
    cd "$ROOT"
    echo "[start] web pid=$(cat pids/web.pid) :$WEB_PORT"
  fi
fi

echo "[start] done — API http://$ORCH_HOST:$ORCH_PORT  WEB http://127.0.0.1:$WEB_PORT"
