#!/usr/bin/env bash
# Mac 侧：SSH 本地转发，把云端 127.0.0.1:5432 映射到本机本地端口
# 用于 push-db-to-cloud（写 newsc）
#
# 用法:
#   bash scripts/deploy/db-tunnel.sh          # 前台
#   bash scripts/deploy/db-tunnel.sh -d       # 后台
#   bash scripts/deploy/db-tunnel.sh --stop
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck disable=SC1091
[[ -f "$ROOT/.env.cloud.local" ]] && set -a && source "$ROOT/.env.cloud.local" && set +a

HOST="${DEPLOY_HOST:-120.25.145.131}"
LOCAL_PORT="${NEWSC_TUNNEL_LOCAL_PORT:-15434}"
REMOTE_PORT=5432
PID_FILE="${TMPDIR:-/tmp}/newsc-db-tunnel.pid"

stop_tunnel() {
  if [[ -f "$PID_FILE" ]]; then
    kill "$(cat "$PID_FILE")" 2>/dev/null || true
    rm -f "$PID_FILE"
    echo "[tunnel] 已停止"
  else
    pkill -f "ssh.*-L ${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT}.*${HOST}" 2>/dev/null || true
    echo "[tunnel] 已尝试清理"
  fi
}

if [[ "${1:-}" == "--stop" ]]; then
  stop_tunnel
  exit 0
fi

if lsof -iTCP:"$LOCAL_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "[tunnel] 本机 :${LOCAL_PORT} 已在监听，跳过"
  exit 0
fi

ARGS=(-N -L "${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT}" -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o BatchMode=yes "root@${HOST}")

if [[ "${1:-}" == "-d" || "${1:-}" == "--daemon" ]]; then
  ssh "${ARGS[@]}" &
  echo $! > "$PID_FILE"
  sleep 1
  echo "[tunnel] 后台 PID=$(cat "$PID_FILE") · 127.0.0.1:${LOCAL_PORT} → ${HOST}:5432"
else
  echo "[tunnel] 前台转发 127.0.0.1:${LOCAL_PORT} → ${HOST}:${REMOTE_PORT}（Ctrl+C 结束）"
  exec ssh "${ARGS[@]}"
fi
