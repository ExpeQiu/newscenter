#!/usr/bin/env bash
# Stop NewsC processes.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  set -a
  source .env
  set +a
fi

stop_pidfile() {
  local f="$1"
  local name="$2"
  if [[ -f "$f" ]]; then
    local pid
    pid="$(cat "$f")"
    if kill -0 "$pid" 2>/dev/null; then
      # 结束进程组（start_new_session 启动）
      kill -- "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
      sleep 0.3
      kill -9 -- "-$pid" 2>/dev/null || kill -9 "$pid" 2>/dev/null || true
      echo "[stop] $name pid=$pid"
    fi
    rm -f "$f"
  fi
}

stop_pidfile pids/web.pid web
stop_pidfile pids/orchestrator.pid orchestrator

echo "[stop] done"
