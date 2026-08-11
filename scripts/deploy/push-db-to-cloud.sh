#!/usr/bin/env bash
# push-db-to-cloud.sh — 将本机 newsc 推送到云端共用 stock-pg 的 newsc 库，并同步 vault
# 真源：Mac 本地 PostgreSQL；云端为副本
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/push-db-to-cloud.log"
STAMP="$(date '+%Y%m%d-%H%M%S')"
DUMP="/tmp/newsc-push-$STAMP.sql"
STRIPPED="/tmp/newsc-push-$STAMP.pg16.sql"
DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

normalize_pg_url() {
  # SQLAlchemy 方言 → libpq / pg_dump 可用 URL
  printf '%s' "$1" | sed 's|^postgresql+psycopg://|postgresql://|'
}

# shellcheck disable=SC1091
[[ -f "$ROOT/.env.cloud.local" ]] && set -a && source "$ROOT/.env.cloud.local" && set +a
# shellcheck disable=SC1091
[[ -f "$ROOT/.env" ]] && set -a && source "$ROOT/.env" && set +a

RAW_LOCAL="${LOCAL_DATABASE_URL:-${DATABASE_URL:-postgresql://qiubin@/newsc?host=/tmp}}"
LOCAL_URL="$(normalize_pg_url "$RAW_LOCAL")"
CLOUD_URL="${CLOUD_DATABASE_URL:-}"
if [[ -z "$CLOUD_URL" ]]; then
  log "✗ 缺少 CLOUD_DATABASE_URL（写在 .env.cloud.local）"
  exit 1
fi
CLOUD_URL="$(normalize_pg_url "$CLOUD_URL")"

LOCAL_PORT="${NEWSC_TUNNEL_LOCAL_PORT:-15434}"

log "════════════════════════════════════════"
log "  Mac → 云 newsc 推送 · $STAMP"
log "════════════════════════════════════════"

# 本机 PG：socket 或 TCP
if ! pg_isready -h /tmp >/dev/null 2>&1 && ! pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
  log "✗ 本机 PostgreSQL 未响应"
  exit 1
fi

if [[ "${SKIP_VAULT_INGEST:-0}" != "1" ]]; then
  log "▶ vault 目录 → DB"
  export PYTHONPATH="$ROOT:$ROOT/collectors/rss-CLI:$ROOT/collectors/youtube-CLI:$ROOT/collectors/bilibili-CLI:$ROOT/collectors/social-CLI:$ROOT/digest-CLI:$ROOT/newsc-CLI:${PYTHONPATH:-}"
  PY="${ROOT}/.venv/bin/python"
  [[ -x "$PY" ]] || PY=python3
  if [[ "$DRY" -eq 1 ]]; then
    "$PY" -m pipeline.vault_ingest | tee -a "$LOG" || log "⚠ vault ingest 失败（dry-run 继续）"
  else
    "$PY" -m pipeline.vault_ingest | tee -a "$LOG"
  fi
else
  log "↷ 跳过 vault ingest（SKIP_VAULT_INGEST=1）"
fi

log "▶ 确保隧道 :${LOCAL_PORT}"
bash "$ROOT/scripts/deploy/db-tunnel.sh" -d
# 等待隧道真正可连（避免刚拉起即 psql 被拒）
for i in 1 2 3 4 5 6 7 8 9 10; do
  if pg_isready -h 127.0.0.1 -p "$LOCAL_PORT" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
  if [[ "$i" -eq 10 ]]; then
    log "✗ 隧道 :${LOCAL_PORT} 未就绪"
    exit 1
  fi
done
log "✓ 隧道就绪"

log "▶ pg_dump newsc"
pg_dump -Fp --no-owner --no-acl --clean --if-exists "$LOCAL_URL" -f "$DUMP"
python3 "$ROOT/scripts/deploy/strip-pg18-dump.py" "$DUMP" "$STRIPPED"
log "✓ dump $(wc -c <"$STRIPPED" | tr -d ' ') bytes"

if [[ "$DRY" -eq 1 ]]; then
  log "↷ dry-run（跳过 restore）"
  rm -f "$DUMP" "$STRIPPED"
  exit 0
fi

log "▶ 恢复到云端"
set +e
psql "$CLOUD_URL" -v ON_ERROR_STOP=1 -f "$STRIPPED" >>"$LOG" 2>&1
RC=$?
set -e
rm -f "$DUMP" "$STRIPPED"
if [[ "$RC" -ne 0 ]]; then
  log "✗ 恢复失败，详见 $LOG"
  exit 1
fi
log "✓ 云端恢复完成"

log "▶ 对账"
export LOCAL_URL CLOUD_URL
PY="${ROOT}/.venv/bin/python"
[[ -x "$PY" ]] || PY=python3
if ! "$PY" "$ROOT/scripts/deploy/compare-db-counts.py"; then
  log "⚠ 对账不一致（详见上方）"
fi

# 可选：仍同步文件系统副本（默认关闭，云端读 DB）
if [[ "${SYNC_VAULT_FILES:-0}" == "1" ]]; then
  log "▶ vault 文件 rsync（SYNC_VAULT_FILES=1）"
  bash "$ROOT/scripts/deploy/sync-vault-to-cloud.sh"
else
  log "↷ 跳过 vault 文件 rsync（日报已入库，随 pg_dump 上云）"
fi

log "════════════════════════════════════════"
log "  推送成功 · 云端数据 = Mac 真源"
log "════════════════════════════════════════"
