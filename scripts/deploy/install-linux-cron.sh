#!/usr/bin/env bash
# 云端：仅健康巡检（禁止 pipeline / ai 写业务表）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
mkdir -p "$ROOT/logs"

WRAPPER="$ROOT/scripts/deploy/run-with-env.sh"
cat > "$WRAPPER" <<EOF
#!/usr/bin/env bash
set -euo pipefail
ROOT="$ROOT"
cd "\$ROOT"
set -a
[[ -f "\$ROOT/.env" ]] && source "\$ROOT/.env"
set +a
export DEPLOY_ENV=cloud
export PATH="/root/.local/bin:/usr/local/bin:/usr/bin:/bin:\$PATH"
exec "\$@"
EOF
chmod +x "$WRAPPER"

CRON_FILE="/etc/cron.d/newsc"
cat > "$CRON_FILE" <<EOF
# NewsC · 云端只读巡检（真源 = Mac 推送）
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin
TZ=Asia/Shanghai

# 健康巡检每小时
25 * * * * root $WRAPPER bash $ROOT/scripts/deploy/verify-cloud.sh >>$ROOT/logs/verify-cloud-cron.log 2>&1
EOF
chmod 644 "$CRON_FILE"

systemctl enable crond 2>/dev/null || systemctl enable cron 2>/dev/null || true
systemctl restart crond 2>/dev/null || systemctl restart cron 2>/dev/null || true

echo "[linux-cron] 已安装: $CRON_FILE"
cat "$CRON_FILE"
