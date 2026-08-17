#!/usr/bin/env bash
# 安装本机订阅采集 LaunchAgent（每 15 分钟）。脚本装在 ~/Library/Application Support/newsc
# 避免 iCloud Desktop/Documents 路径被 launchd TCC 拒绝。
set -euo pipefail
SELF="${BASH_SOURCE[0]:-$0}"
REPO="$(cd "$(dirname "$SELF")/.." && pwd)"
APP_SUPPORT="${HOME}/Library/Application Support/newsc"
LABEL="com.newsc.pipeline-sources"
PLIST_PATH="${HOME}/Library/LaunchAgents/${LABEL}.plist"
WRAPPER="${APP_SUPPORT}/run-pipeline-sources.sh"
LOG_DIR="${APP_SUPPORT}/logs"
ACTION="${1:-install}"
API_URL="${NEWSC_API_URL:-http://127.0.0.1:8787}"

uninstall() {
  launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
  rm -f "${PLIST_PATH}"
  echo "[pipeline-sources] uninstalled: ${LABEL}"
}

if [[ "${ACTION}" == "uninstall" || "${ACTION}" == "off" ]]; then
  uninstall
  exit 0
fi

mkdir -p "${LOG_DIR}" "${HOME}/Library/LaunchAgents"

cat > "${WRAPPER}" <<EOF
#!/usr/bin/env bash
set -euo pipefail
API="\${NEWSC_API_URL:-${API_URL}}"
LOG="${LOG_DIR}/pipeline-sources.log"
stamp() { date '+%H:%M:%S'; }
echo "[\$(stamp)] pipeline run sources" >>"\$LOG"
code=\$(curl -sS -o /tmp/newsc-pipeline-sources.json -w '%{http_code}' \\
  -X POST "\${API}/pipelines/sources/run" \\
  -H 'Content-Type: application/json' \\
  --connect-timeout 5 --max-time 300 || echo 000)
echo "[\$(stamp)] sources http=\$code \$(head -c 400 /tmp/newsc-pipeline-sources.json 2>/dev/null)" >>"\$LOG"
[[ "\$code" == "200" ]] || exit 1
echo "[\$(stamp)] vault ingest" >>"\$LOG"
vcode=\$(curl -sS -o /tmp/newsc-vault-ingest.json -w '%{http_code}' \\
  -X POST "\${API}/digests/vault/ingest" \\
  -H 'Content-Type: application/json' \\
  --connect-timeout 5 --max-time 300 || echo 000)
echo "[\$(stamp)] vault http=\$vcode \$(head -c 400 /tmp/newsc-vault-ingest.json 2>/dev/null)" >>"\$LOG"
[[ "\$vcode" == "200" ]] || exit 1
echo "[\$(stamp)] insight retrieve" >>"\$LOG"
icode=\$(curl -sS -o /tmp/newsc-insight.json -w '%{http_code}' \\
  -X POST "\${API}/pipelines/insight/run?force=false&kind=all" \\
  -H 'Content-Type: application/json' \\
  --connect-timeout 5 --max-time 600 || echo 000)
echo "[\$(stamp)] insight http=\$icode \$(head -c 400 /tmp/newsc-insight.json 2>/dev/null)" >>"\$LOG"
# insight 失败不阻断采集主链
true
EOF
chmod +x "${WRAPPER}"

if [[ -d "${REPO}/scripts" ]]; then
  cat > "${REPO}/scripts/run-pipeline-sources.sh" <<'EOF'
#!/usr/bin/env bash
# 转发到 Application Support 中的实际脚本（由 install-pipeline-sources-launchd.sh 安装）
exec "${HOME}/Library/Application Support/newsc/run-pipeline-sources.sh" "$@"
EOF
  chmod +x "${REPO}/scripts/run-pipeline-sources.sh"
fi

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
  <integer>900</integer>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/pipeline-sources-launchd.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/pipeline-sources-launchd-err.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    <key>HOME</key>
    <string>${HOME}</string>
    <key>NEWSC_API_URL</key>
    <string>${API_URL}</string>
  </dict>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "${PLIST_PATH}"
launchctl kickstart -k "gui/$(id -u)/${LABEL}" 2>/dev/null || true
echo "[pipeline-sources] installed: ${PLIST_PATH}"
echo "[pipeline-sources] wrapper: ${WRAPPER}"
echo "[pipeline-sources] interval: 900s (source refresh_interval still gates fetch)"
echo "[pipeline-sources] log: ${LOG_DIR}/pipeline-sources.log"
