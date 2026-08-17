#!/usr/bin/env bash
# 安装 Mac 控制面 Agent（每 2 分钟拉 marks + drain outbox + sources 对账）
# 脚本与 .env 副本装在 ~/Library/Application Support/newsc，避免 iCloud 路径被 launchd TCC 拒绝。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APP_SUPPORT="${HOME}/Library/Application Support/newsc"
LABEL="com.newsc.cloud-bridge"
PLIST_PATH="${HOME}/Library/LaunchAgents/${LABEL}.plist"
WRAPPER="${APP_SUPPORT}/run-cloud-bridge.sh"
ENV_COPY="${APP_SUPPORT}/.env.cloud.local"
LOG_DIR="${APP_SUPPORT}/logs"
ACTION="${1:-install}"

uninstall() {
  launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
  rm -f "${PLIST_PATH}"
  echo "[cloud-bridge] uninstalled: ${LABEL}"
}

if [[ "${ACTION}" == "uninstall" || "${ACTION}" == "off" ]]; then
  uninstall
  exit 0
fi

mkdir -p "${LOG_DIR}" "${HOME}/Library/LaunchAgents" "${ROOT}/logs"

# 环境文件副本：launchd 往往无法 source iCloud 下的 .env.cloud.local
if [[ -f "${ROOT}/.env.cloud.local" ]]; then
  cp -f "${ROOT}/.env.cloud.local" "${ENV_COPY}"
  chmod 600 "${ENV_COPY}"
  echo "[cloud-bridge] synced env → ${ENV_COPY}"
elif [[ ! -f "${ENV_COPY}" ]]; then
  echo "[cloud-bridge] ⚠ 缺少 ${ROOT}/.env.cloud.local 与 ${ENV_COPY}" >&2
fi

# 包装器写在非 iCloud 路径；内部再 cd 到仓库执行
cat > "${WRAPPER}" <<EOF
#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT}"
APP_SUPPORT="${APP_SUPPORT}"
LOG_DIR="${LOG_DIR}"
ENV_COPY="${ENV_COPY}"
mkdir -p "\$LOG_DIR" "\$ROOT/logs"
LOG="\$LOG_DIR/cloud-bridge.log"
stamp() { date '+%H:%M:%S'; }
echo "[\$(stamp)] ▶ cloud_bridge root=\$ROOT" >>"\$LOG"

# 仅从 Application Support 读环境（避免 iCloud TCC）
if [[ -f "\$ENV_COPY" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "\$ENV_COPY"
  set +a
else
  echo "[\$(stamp)] x missing \$ENV_COPY（请重装 install-cloud-bridge-launchd.sh）" >>"\$LOG"
  exit 1
fi

cd "\$ROOT" || {
  echo "[\$(stamp)] x cd ROOT failed (iCloud/TCC?) root=\$ROOT" >>"\$LOG"
  exit 1
}

export PYTHONPATH="\$ROOT:\$ROOT/collectors/rss-CLI:\$ROOT/collectors/youtube-CLI:\$ROOT/collectors/bilibili-CLI:\$ROOT/collectors/social-CLI:\$ROOT/digest-CLI:\$ROOT/newsc-CLI:\${PYTHONPATH:-}"
PY="\$ROOT/.venv/bin/python"
if [[ ! -x "\$PY" ]]; then
  PY="\$(command -v python3 || true)"
fi
if [[ -z "\$PY" ]]; then
  echo "[\$(stamp)] x python not found" >>"\$LOG"
  exit 1
fi

set +e
"\$PY" -m pipeline.cloud_bridge >>"\$LOG" 2>&1
RC=\$?
set -e
if [[ "\$RC" -ne 0 ]]; then
  echo "[\$(stamp)] x cloud_bridge rc=\$RC" >>"\$LOG"
  exit "\$RC"
fi
echo "[\$(stamp)] ok cloud_bridge" >>"\$LOG"
cp -f "\$LOG" "\$ROOT/logs/cloud-bridge-launchd.log" 2>/dev/null || true
EOF
chmod +x "${WRAPPER}"

# 仓库内脚本改为转发到 Application Support（手动执行也走同一路径）
cat > "${ROOT}/scripts/deploy/pull-cloud-control.sh" <<'EOF'
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
EOF
chmod +x "${ROOT}/scripts/deploy/pull-cloud-control.sh"

cat > "${PLIST_PATH}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${WRAPPER}</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>StartInterval</key>
  <integer>120</integer>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/cloud-bridge-launchd.out</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/cloud-bridge-launchd.err</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    <key>HOME</key>
    <string>${HOME}</string>
  </dict>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "${PLIST_PATH}"
launchctl kickstart -k "gui/$(id -u)/${LABEL}" 2>/dev/null || true
echo "[cloud-bridge] installed: ${PLIST_PATH}"
echo "[cloud-bridge] wrapper: ${WRAPPER}"
echo "[cloud-bridge] env: ${ENV_COPY}"
echo "[cloud-bridge] interval: 120s"
echo "[cloud-bridge] log: ${LOG_DIR}/cloud-bridge.log"
echo "[cloud-bridge] manual: bash ${ROOT}/scripts/deploy/pull-cloud-control.sh"
