#!/usr/bin/env bash
# sync-vault-to-cloud.sh — 将 digest vault 目录同步到云端 /opt/newsc/vault-data/<id>/
# 并写入远端 digest-sources.local.yml（相对路径，供云 API 读取）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ROOT="${NEWSC_ROOT:-$ROOT}"
cd "$ROOT"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/sync-vault-to-cloud.log"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

# shellcheck disable=SC1091
APP_ENV="${HOME}/Library/Application Support/newsc/.env.cloud.local"
if [[ -f "$APP_ENV" ]]; then
  set -a && source "$APP_ENV" && set +a
elif [[ -f "$ROOT/.env.cloud.local" ]]; then
  set -a && source "$ROOT/.env.cloud.local" && set +a
fi

HOST="${DEPLOY_HOST:-120.25.145.131}"
REMOTE_USER="${DEPLOY_USER:-root}"
REMOTE="${REMOTE_USER}@${HOST}"
REMOTE_DIR="${DEPLOY_DIR:-/opt/newsc}"
DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1

export ROOT
MAP_JSON="$(
  python3 - <<'PY'
import json
import os
from pathlib import Path

import yaml

root = Path(os.environ["ROOT"])
base = root / "digest-sources.yml"
local = root / "digest-sources.local.yml"

def load(p: Path):
    if not p.is_file():
        return []
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    items = raw.get("sources") if isinstance(raw, dict) else None
    return [i for i in items if isinstance(i, dict)] if isinstance(items, list) else []

by_id = {}
order = []
deleted = set()
for item in load(base) + load(local):
    sid = str(item.get("id") or "").strip()
    if not sid:
        continue
    if item.get("deleted") is True:
        deleted.add(sid)
        by_id.pop(sid, None)
        continue
    deleted.discard(sid)
    if sid not in by_id and sid not in order:
        order.append(sid)
    by_id[sid] = item

out = []
for sid in order:
    if sid in deleted or sid not in by_id:
        continue
    item = by_id[sid]
    if not bool(item.get("enabled", True)):
        continue
    path_raw = str(item.get("path") or "").strip().strip('"').strip("'")
    if not path_raw:
        continue
    p = Path(path_raw).expanduser()
    if not p.is_absolute():
        p = (root / p).resolve()
    else:
        p = p.resolve()
    out.append({
        "id": sid,
        "label": str(item.get("label") or sid).strip() or sid,
        "src": str(p),
        "enabled": True,
    })
print(json.dumps(out, ensure_ascii=False))
PY
)"

COUNT=$(MAP_JSON="$MAP_JSON" python3 -c "import json,os; print(len(json.loads(os.environ['MAP_JSON'])))")
log "════════════════════════════════════════"
log "  vault → 云 · ${COUNT} 个来源"
log "════════════════════════════════════════"

if [[ "$COUNT" == "0" ]]; then
  log "↷ 无启用中的 vault 来源"
  exit 0
fi

if [[ "$DRY" -eq 1 ]]; then
  MAP_JSON="$MAP_JSON" python3 -c "import json,os; [print(f\"  {x['id']}: {x['src']}\") for x in json.loads(os.environ['MAP_JSON'])]"
  log "↷ dry-run"
  exit 0
fi

ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$REMOTE" "mkdir -p ${REMOTE_DIR}/vault-data ${REMOTE_DIR}/logs"

CLOUD_YML="$(
  MAP_JSON="$MAP_JSON" python3 - <<'PY'
import json
import os

items = json.loads(os.environ["MAP_JSON"])
lines = ["# 由 sync-vault-to-cloud.sh 生成 · 勿手改", "sources:"]
for x in items:
    lines.append(f"- id: {x['id']}")
    lines.append(f"  label: {x['label']}")
    lines.append(f"  path: vault-data/{x['id']}")
    lines.append("  enabled: true")
print("\n".join(lines) + "\n")
PY
)"

TMP_YML="$(mktemp)"
printf '%s' "$CLOUD_YML" > "$TMP_YML"
scp -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$TMP_YML" "${REMOTE}:${REMOTE_DIR}/digest-sources.local.yml"
rm -f "$TMP_YML"
log "✓ 已写远端 digest-sources.local.yml"

while IFS= read -r line; do
  [[ -z "$line" ]] && continue
  SID=$(LINE="$line" python3 -c "import json,os; print(json.loads(os.environ['LINE'])['id'])")
  SRC=$(LINE="$line" python3 -c "import json,os; print(json.loads(os.environ['LINE'])['src'])")
  if [[ ! -d "$SRC" ]]; then
    log "⚠ 跳过缺失目录 id=$SID path=$SRC"
    continue
  fi
  log "▶ rsync $SID ← $SRC"
  rsync -az --delete \
    -e "ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new" \
    "$SRC/" "${REMOTE}:${REMOTE_DIR}/vault-data/${SID}/"
  log "✓ $SID"
done < <(MAP_JSON="$MAP_JSON" python3 -c "import json,os; print('\n'.join(json.dumps(x, ensure_ascii=False) for x in json.loads(os.environ['MAP_JSON'])))")

log "════════════════════════════════════════"
log "  vault 同步完成"
log "════════════════════════════════════════"
