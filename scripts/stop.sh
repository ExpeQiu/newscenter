#!/usr/bin/env bash
# Stop NewsC processes.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

stop_pidfile() {
  local f="$1"
  local name="$2"
  if [[ -f "$f" ]]; then
    local pid
    pid="$(cat "$f")"
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      sleep 0.3
      kill -9 "$pid" 2>/dev/null || true
      echo "[stop] $name pid=$pid"
    fi
    rm -f "$f"
  fi
}

stop_pidfile pids/web.pid web
stop_pidfile pids/orchestrator.pid orchestrator

# also clear listeners if leftover
ORCH_PORT="${ORCH_PORT:-8787}"
WEB_PORT="${WEB_PORT:-3000}"
if command -v lsof >/dev/null; then
  for p in "$ORCH_PORT" "$WEB_PORT"; do
    pids=$(lsof -tiTCP:"$p" -sTCP:LISTEN 2>/dev/null || true)
    if [[ -n "${pids:-}" ]]; then
      echo "[stop] freeing port $p: $pids"
      kill $pids 2>/dev/null || true
    fi
  done
fi

echo "[stop] done"
