#!/usr/bin/env bash
# 安装 Mac 控制面 Agent（每 2 分钟拉 marks + drain outbox）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LABEL="com.newsc.cloud-bridge"
PLIST_PATH="${HOME}/Library/LaunchAgents/${LABEL}.plist"
PULL="${ROOT}/scripts/deploy/pull-cloud-control.sh"
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

chmod +x "${PULL}"
mkdir -p "${ROOT}/logs"
mkdir -p "${HOME}/Library/LaunchAgents"

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
    <string>${PULL}</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>StartInterval</key>
  <integer>120</integer>
  <key>StandardOutPath</key>
  <string>${ROOT}/logs/cloud-bridge-launchd.log</string>
  <key>StandardErrorPath</key>
  <string>${ROOT}/logs/cloud-bridge-launchd-err.log</string>
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
echo "[cloud-bridge] installed: ${PLIST_PATH}"
echo "[cloud-bridge] interval: 120s"
echo "[cloud-bridge] manual: bash ${PULL}"
