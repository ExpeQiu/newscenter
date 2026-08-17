#!/usr/bin/env bash
# pull-cloud-control.sh — 转发到 Application Support 包装器（避免 iCloud + launchd TCC）
set -euo pipefail
WRAPPER="${HOME}/Library/Application Support/newsc/run-cloud-bridge.sh"
if [[ ! -x "$WRAPPER" ]]; then
  echo "[pull-cloud-control] 缺少包装器，请先: bash scripts/deploy/install-cloud-bridge-launchd.sh" >&2
  exit 1
fi
# 手动执行前刷新 env 副本（交互 shell 可读 iCloud）
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_COPY="${HOME}/Library/Application Support/newsc/.env.cloud.local"
if [[ -f "${ROOT}/.env.cloud.local" ]]; then
  cp -f "${ROOT}/.env.cloud.local" "${ENV_COPY}"
  chmod 600 "${ENV_COPY}"
fi
exec "$WRAPPER" "$@"
