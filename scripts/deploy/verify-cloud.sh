#!/usr/bin/env bash
# 云端只读巡检（禁止跑采集 / AI 写库）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
# shellcheck disable=SC1091
[[ -f "$ROOT/.env" ]] && set -a && source "$ROOT/.env" && set +a

ORCH_HOST="${ORCH_HOST:-127.0.0.1}"
ORCH_PORT="${ORCH_PORT:-8787}"
WEB_PORT="${WEB_PORT:-8333}"

echo "[verify-cloud] api health"
curl -sf -m 10 "http://${ORCH_HOST}:${ORCH_PORT}/health" | tee /dev/stderr | grep -q '"ok"'

echo "[verify-cloud] web"
CODE=$(curl -s -o /dev/null -w "%{http_code}" -m 10 "http://127.0.0.1:${WEB_PORT}/")
[[ "$CODE" == "200" || "$CODE" == "304" ]] || {
  echo "web HTTP $CODE" >&2
  exit 1
}

echo "[verify-cloud] vault status (read-only)"
curl -sf -m 10 "http://${ORCH_HOST}:${ORCH_PORT}/digests/vault/status" >/dev/null || true

echo "[verify-cloud] ok"
