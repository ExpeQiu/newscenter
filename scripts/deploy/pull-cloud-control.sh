#!/usr/bin/env bash
# pull-cloud-control.sh — Mac 拉取云端 marks + 消费 outbox（A/B/C 控制面）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/pull-cloud-control.log"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

# shellcheck disable=SC1091
[[ -f "$ROOT/.env.cloud.local" ]] && set -a && source "$ROOT/.env.cloud.local" && set +a
# shellcheck disable=SC1091
[[ -f "$ROOT/.env" ]] && set -a && source "$ROOT/.env" && set +a

export PYTHONPATH="$ROOT:$ROOT/collectors/rss-CLI:$ROOT/collectors/youtube-CLI:$ROOT/collectors/bilibili-CLI:$ROOT/collectors/social-CLI:$ROOT/digest-CLI:$ROOT/newsc-CLI:${PYTHONPATH:-}"
PY="${ROOT}/.venv/bin/python"
[[ -x "$PY" ]] || PY=python3

log "▶ cloud_bridge"
set +e
"$PY" -m pipeline.cloud_bridge >>"$LOG" 2>&1
RC=$?
set -e
if [[ "$RC" -ne 0 ]]; then
  log "x cloud_bridge rc=${RC} see ${LOG}"
  exit "${RC}"
fi
log "ok cloud_bridge"
