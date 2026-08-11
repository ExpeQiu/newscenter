#!/usr/bin/env bash
# 安装 / 卸载 Mac→云 整库推送 LaunchAgent
# 配置来自 .env.cloud.local：
#   PUSH_SCHEDULE_ENABLED=1|0
#   PUSH_SCHEDULE_MODE=daily|interval
#   PUSH_SCHEDULE_TIMES=08:25,12:15,18:25,21:15   # daily
#   PUSH_SCHEDULE_INTERVAL_HOURS=6               # interval
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LABEL="com.newsc.push-db-cloud"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
PUSH="$ROOT/scripts/deploy/push-db-to-cloud.sh"
LOG_DIR="$ROOT/logs"
ACTION="${1:-install}"

# shellcheck disable=SC1091
[[ -f "$ROOT/.env.cloud.local" ]] && set -a && source "$ROOT/.env.cloud.local" && set +a

ENABLED="${PUSH_SCHEDULE_ENABLED:-1}"
MODE="${PUSH_SCHEDULE_MODE:-daily}"
TIMES="${PUSH_SCHEDULE_TIMES:-08:25,12:15,18:25,21:15}"
INTERVAL_H="${PUSH_SCHEDULE_INTERVAL_HOURS:-6}"

uninstall() {
  launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
  rm -f "$PLIST"
  echo "[push-db-cloud] 已卸载定时推送: $LABEL"
}

if [[ "$ACTION" == "uninstall" || "$ACTION" == "off" ]]; then
  uninstall
  exit 0
fi

if [[ "$ACTION" == "status" ]]; then
  if [[ -f "$PLIST" ]] && launchctl print "gui/$(id -u)/${LABEL}" >/dev/null 2>&1; then
    echo "installed=1"
    exit 0
  fi
  echo "installed=0"
  exit 1
fi

# install / apply
if [[ "$ENABLED" != "1" && "$ENABLED" != "true" && "$ENABLED" != "yes" ]]; then
  uninstall
  exit 0
fi

chmod +x "$PUSH"
mkdir -p "$LOG_DIR"

SCHEDULE_XML=""
if [[ "$MODE" == "interval" ]]; then
  if ! [[ "$INTERVAL_H" =~ ^[0-9]+$ ]] || [[ "$INTERVAL_H" -lt 1 ]] || [[ "$INTERVAL_H" -gt 168 ]]; then
    echo "[push-db-cloud] ✗ PUSH_SCHEDULE_INTERVAL_HOURS 无效: $INTERVAL_H" >&2
    exit 2
  fi
  SECS=$((INTERVAL_H * 3600))
  SCHEDULE_XML="  <key>StartInterval</key>
  <integer>${SECS}</integer>"
  echo "[push-db-cloud] 周期: 每 ${INTERVAL_H} 小时"
else
  # daily calendar times
  TIMES_XML="  <array>"
  IFS=',' read -r -a ARR <<< "$TIMES"
  COUNT=0
  for t in "${ARR[@]}"; do
    t="$(echo "$t" | tr -d '[:space:]')"
    [[ -z "$t" ]] && continue
    if [[ ! "$t" =~ ^([0-1]?[0-9]|2[0-3]):([0-5][0-9])$ ]]; then
      echo "[push-db-cloud] ✗ 时刻格式无效: $t（需 HH:MM）" >&2
      exit 2
    fi
    H="${BASH_REMATCH[1]}"
    M="${BASH_REMATCH[2]}"
    # 去掉前导零，避免 08 被 octal 解析
    H=$((10#$H))
    M=$((10#$M))
    TIMES_XML+=$'\n'"    <dict><key>Hour</key><integer>${H}</integer><key>Minute</key><integer>${M}</integer></dict>"
    COUNT=$((COUNT + 1))
  done
  TIMES_XML+=$'\n'"  </array>"
  if [[ "$COUNT" -eq 0 ]]; then
    echo "[push-db-cloud] ✗ PUSH_SCHEDULE_TIMES 为空" >&2
    exit 2
  fi
  SCHEDULE_XML="  <key>StartCalendarInterval</key>
${TIMES_XML}"
  echo "[push-db-cloud] 每日定点: $TIMES"
fi

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${PUSH}</string>
  </array>
  <key>RunAtLoad</key>
  <false/>
${SCHEDULE_XML}
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/push-db-cloud-launchd.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/push-db-cloud-launchd-err.log</string>
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
launchctl bootstrap "gui/$(id -u)" "$PLIST"

echo "[push-db-cloud] 已安装: $PLIST"
echo "[push-db-cloud] 手动: bash $PUSH"
