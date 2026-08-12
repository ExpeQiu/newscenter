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

export PYTHONPATH="$ROOT:$ROOT/collectors/rss-CLI:$ROOT/collectors/youtube-CLI:$ROOT/collectors/bilibili-CLI:$ROOT/collectors/social-CLI:$ROOT/digest-CLI:$ROOT/newsc-CLI:${PYTHONPATH:-}"

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

port_pids() {
  local port="$1"
  lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | sort -u || true
}

# 若 pidfile 失效但端口仍被占用，同步 pidfile，避免再起一个绑不上的僵尸进程
sync_pidfile_from_port() {
  local port="$1"
  local pidfile="$2"
  local name="$3"
  local listeners
  listeners="$(port_pids "$port")"
  if [[ -z "$listeners" ]]; then
    return 1
  fi
  local first
  first="$(echo "$listeners" | head -1)"
  echo "$first" >"$pidfile"
  echo "[start] $name port :$port already listening pid=$first (synced pidfile)"
  return 0
}

if [[ -f pids/orchestrator.pid ]] && kill -0 "$(cat pids/orchestrator.pid)" 2>/dev/null; then
  echo "[start] orchestrator already running pid=$(cat pids/orchestrator.pid)"
elif sync_pidfile_from_port "$ORCH_PORT" pids/orchestrator.pid orchestrator; then
  :
else
  # start_new_session：避免父 shell 退出时带走进程
  python - <<PY
import subprocess
from pathlib import Path
log = open("logs/orchestrator.log", "ab", buffering=0)
p = subprocess.Popen(
    ["uvicorn", "orchestrator.main:app", "--host", "$ORCH_HOST", "--port", "$ORCH_PORT"],
    stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
)
Path("pids/orchestrator.pid").write_text(str(p.pid))
print(f"[start] orchestrator pid={p.pid} :$ORCH_PORT")
PY
fi

# wait health + 确认笔记路由已加载（避免旧进程占端口却误报成功）
for i in $(seq 1 30); do
  if curl -sf "http://$ORCH_HOST:$ORCH_PORT/health" >/dev/null \
    && curl -sf "http://$ORCH_HOST:$ORCH_PORT/note-columns" >/dev/null; then
    echo "[start] health ok"
    break
  fi
  sleep 0.3
  if [[ $i -eq 30 ]]; then
    echo "[start] health timeout（或笔记路由缺失，请 ./scripts/stop.sh 后重试）" >&2
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
  elif sync_pidfile_from_port "$WEB_PORT" pids/web.pid web; then
    :
  else
    python - <<PY
import subprocess
from pathlib import Path
log = open("logs/web.log", "ab", buffering=0)
p = subprocess.Popen(
    ["npm", "run", "dev", "--", "-p", "$WEB_PORT"],
    cwd="apps/web", stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
)
Path("pids/web.pid").write_text(str(p.pid))
print(f"[start] web pid={p.pid} :$WEB_PORT")
PY
  fi
fi

echo "[start] done — API http://$ORCH_HOST:$ORCH_PORT  WEB http://127.0.0.1:$WEB_PORT"
