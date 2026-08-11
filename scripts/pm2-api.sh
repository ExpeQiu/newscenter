#!/usr/bin/env bash
# PM2 入口：加载 .env + PYTHONPATH 后启动 orchestrator
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
set -a && source "$ROOT/.env" && set +a
export PYTHONPATH="$ROOT:$ROOT/collectors/rss-CLI:$ROOT/collectors/youtube-CLI:$ROOT/collectors/bilibili-CLI:$ROOT/collectors/social-CLI:$ROOT/digest-CLI:$ROOT/newsc-CLI:${PYTHONPATH:-}"
ORCH_HOST="${ORCH_HOST:-127.0.0.1}"
ORCH_PORT="${ORCH_PORT:-8787}"
exec "$ROOT/.venv/bin/uvicorn" orchestrator.main:app --host "$ORCH_HOST" --port "$ORCH_PORT"
