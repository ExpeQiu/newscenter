#!/usr/bin/env bash
# deploy-aliyun.sh — 部署 NewsC 到阿里云 120（共用 stock-pg + PM2）
# 用法:
#   export DEPLOY_HOST=120.25.145.131
#   bash scripts/deploy/deploy-aliyun.sh
# 可选: SKIP_DB=1 SKIP_SYNC_INSTALL=1 SKIP_BUILD=1 FORCE_DB_RESTORE=1 DUMP_FILE=/path.sql
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

HOST="${DEPLOY_HOST:-120.25.145.131}"
REMOTE_USER="${DEPLOY_USER:-root}"
REMOTE="${REMOTE_USER}@${HOST}"
REMOTE_DIR="${DEPLOY_DIR:-/opt/newsc}"
SSH=(ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new)
SCP=(scp -o BatchMode=yes -o StrictHostKeyChecking=accept-new)
RSYNC=(rsync -az --delete
  --exclude node_modules
  --exclude .next
  --exclude .git
  --exclude logs
  --exclude pids
  --exclude .venv
  --exclude .npm-cache
  --exclude '.env'
  --exclude '.env.cloud.local'
  --exclude 'deploy/.env.pg'
  --exclude 'digest-sources.local.yml'
  --exclude 'vault-data'
  --exclude '*.dump'
  --exclude '*.sql'
)

# 避免本机开发 .env 的 WEB_PORT 污染云端端口；可用 DEPLOY_WEB_PORT 覆盖
WEB_PORT="${DEPLOY_WEB_PORT:-8333}"
ORCH_PORT="${DEPLOY_ORCH_PORT:-8787}"
PG_PASS_DIR="/tmp/newsc-deploy"
PG_PASS_FILE="${PG_PASS_FILE:-$PG_PASS_DIR/pg_pass.txt}"
TOKEN_FILE="${TOKEN_FILE:-$PG_PASS_DIR/api_token.txt}"

log() { echo "[$(date '+%H:%M:%S')] $*"; }
remote() { "${SSH[@]}" "$REMOTE" "$@"; }

log "════════════════════════════════════════"
log "  NewsC → ${REMOTE}:${REMOTE_DIR}"
log "════════════════════════════════════════"

# 0. 连通性
remote "echo ok && hostname" >/dev/null
log "✓ SSH ${HOST}"

# 1. 远端目录与基础包
log "▶ 远端基础依赖"
remote "bash -s" <<EOS
set -euo pipefail
export PATH="/root/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
mkdir -p ${REMOTE_DIR}/logs ${REMOTE_DIR}/deploy ${REMOTE_DIR}/vault-data ${REMOTE_DIR}/pids

if ! command -v node >/dev/null 2>&1; then
  echo "✗ 未安装 Node，请先部署 stock 或安装 Node 20+"
  exit 1
fi
if ! command -v pm2 >/dev/null 2>&1; then
  npm install -g pm2
fi

if [[ ! -x ${REMOTE_DIR}/.venv/bin/python ]]; then
  if ! command -v uv >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
  fi
  export PATH="/root/.local/bin:\$PATH"
  uv python install 3.11
  uv venv ${REMOTE_DIR}/.venv --python 3.11
fi
export PATH="/root/.local/bin:\$PATH"

if ! command -v psql >/dev/null 2>&1; then
  yum install -y postgresql 2>&1 | tail -5 || true
fi
if ! command -v rsync >/dev/null 2>&1; then
  yum install -y rsync 2>&1 | tail -5 || true
fi

if command -v firewall-cmd >/dev/null 2>&1; then
  firewall-cmd --permanent --add-port=${WEB_PORT}/tcp 2>/dev/null || true
  firewall-cmd --reload 2>/dev/null || true
fi
EOS
log "✓ 依赖就绪"

# 2. 同步代码
log "▶ rsync 代码"
"${RSYNC[@]}" "$ROOT/" "${REMOTE}:${REMOTE_DIR}/"
log "✓ 代码已同步"

# 3. 共用 stock-pg：建库 + 可选恢复
if [[ "${SKIP_DB:-0}" != "1" ]]; then
  log "▶ 检测共用 stock-pg"
  if ! remote "docker exec stock-pg pg_isready -U stock -d invest" >/dev/null 2>&1; then
    log "✗ stock-pg 未就绪。请先部署 stock 的 Docker PG，勿再起第二套容器。"
    exit 1
  fi
  log "✓ stock-pg healthy"

  mkdir -p "$PG_PASS_DIR"
  if [[ ! -f "$PG_PASS_FILE" ]]; then
    openssl rand -hex 12 > "$PG_PASS_FILE"
  fi
  NC_PASS="$(cat "$PG_PASS_FILE")"
  ENC_PASS=$(python3 -c "import urllib.parse; print(urllib.parse.quote('''${NC_PASS}''', safe=''))")

  if [[ ! -f "$TOKEN_FILE" ]]; then
    openssl rand -hex 16 > "$TOKEN_FILE"
  fi
  API_TOKEN="$(cat "$TOKEN_FILE")"

  STOCK_PASS=$(remote "grep '^POSTGRES_PASSWORD=' /opt/stock/deploy/.env.pg | cut -d= -f2-" || true)
  if [[ -z "$STOCK_PASS" ]]; then
    log "✗ 无法读取 /opt/stock/deploy/.env.pg"
    exit 1
  fi

  remote "cat > ${REMOTE_DIR}/deploy/.env.pg" <<EOF
POSTGRES_USER=newsc
POSTGRES_PASSWORD=${NC_PASS}
POSTGRES_DB=newsc
SHARED_PG_CONTAINER=stock-pg
EOF
  remote "chmod 600 ${REMOTE_DIR}/deploy/.env.pg"

  log "▶ CREATE DATABASE/USER newsc（幂等）"
  remote "STOCK_PASS=\$(grep '^POSTGRES_PASSWORD=' /opt/stock/deploy/.env.pg | cut -d= -f2-)
docker exec -e PGPASSWORD=\"\$STOCK_PASS\" stock-pg psql -U stock -d postgres -tAc \"SELECT 1 FROM pg_roles WHERE rolname='newsc'\" | grep -q 1 \\
  && docker exec -e PGPASSWORD=\"\$STOCK_PASS\" stock-pg psql -U stock -d postgres -c \"ALTER ROLE newsc WITH PASSWORD '${NC_PASS}';\" \\
  || docker exec -e PGPASSWORD=\"\$STOCK_PASS\" stock-pg psql -U stock -d postgres -c \"CREATE ROLE newsc LOGIN PASSWORD '${NC_PASS}';\"
docker exec -e PGPASSWORD=\"\$STOCK_PASS\" stock-pg psql -U stock -d postgres -tAc \"SELECT 1 FROM pg_database WHERE datname='newsc'\" | grep -q 1 \\
  || docker exec -e PGPASSWORD=\"\$STOCK_PASS\" stock-pg psql -U stock -d postgres -c \"CREATE DATABASE newsc OWNER newsc;\"
docker exec -e PGPASSWORD=\"\$STOCK_PASS\" stock-pg psql -U stock -d postgres -c \"GRANT ALL PRIVILEGES ON DATABASE newsc TO newsc;\"
docker exec -e PGPASSWORD=\"\$STOCK_PASS\" stock-pg psql -U stock -d newsc -c \"GRANT ALL ON SCHEMA public TO newsc; ALTER SCHEMA public OWNER TO newsc;\""
  log "✓ newsc 库就绪"

  DUMP_FILE="${DUMP_FILE:-}"
  if [[ -z "$DUMP_FILE" ]]; then
    if [[ -f /tmp/newsc-deploy/newsc.sql ]]; then
      DUMP_FILE=/tmp/newsc-deploy/newsc.sql
    fi
  fi

  HAS_TBL=$(remote "PGPASSWORD=${NC_PASS} psql -h 127.0.0.1 -U newsc -d newsc -t -A -c \"SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';\"" || echo 0)
  if [[ -f "$DUMP_FILE" ]]; then
    if [[ "${FORCE_DB_RESTORE:-0}" == "1" || "$HAS_TBL" == "0" ]]; then
      log "▶ 恢复 dump → newsc"
      STRIPPED="/tmp/newsc-deploy/newsc.pg16.sql"
      mkdir -p /tmp/newsc-deploy
      python3 "$ROOT/scripts/deploy/strip-pg18-dump.py" "$DUMP_FILE" "$STRIPPED"
      "${SCP[@]}" "$STRIPPED" "${REMOTE}:/tmp/newsc.sql"
      remote "docker cp /tmp/newsc.sql stock-pg:/tmp/newsc.sql"
      remote "docker exec -e PGPASSWORD=${NC_PASS} stock-pg psql -U newsc -d newsc -v ON_ERROR_STOP=0 -f /tmp/newsc.sql" || true
      remote "rm -f /tmp/newsc.sql; docker exec stock-pg rm -f /tmp/newsc.sql"
      log "✓ dump 已恢复"
    else
      log "↷ 库已有 ${HAS_TBL} 张表，跳过 restore（FORCE_DB_RESTORE=1 可强制）"
    fi
  else
    log "⚠ 无 dump 文件，将靠 init_db 建表；日常数据请 bash scripts/deploy/push-db-to-cloud.sh"
  fi

  remote "cat > ${REMOTE_DIR}/.env" <<EOF
DATABASE_URL=postgresql+psycopg://newsc:${ENC_PASS}@127.0.0.1:5432/newsc
ORCH_HOST=127.0.0.1
ORCH_PORT=${ORCH_PORT}
WEB_PORT=${WEB_PORT}
NEXT_PUBLIC_API_BASE=/api
ORCH_INTERNAL_URL=http://127.0.0.1:${ORCH_PORT}
ORCH_CORS_ORIGINS=http://${HOST}:${WEB_PORT}
ORCH_API_TOKEN=${API_TOKEN}
AI_MOCK_MODE=true
AI_PROVIDER=mock
LOG_LEVEL=INFO
DEPLOY_ENV=cloud
TZ=Asia/Shanghai
DIGEST_SOURCES_FILE=digest-sources.yml
EOF
  remote "chmod 600 ${REMOTE_DIR}/.env"
  log "✓ .env 已写入"

  cat > "$ROOT/.env.cloud.local" <<EOF
# 由 deploy-aliyun.sh 生成 · 勿提交
DEPLOY_HOST=${HOST}
DEPLOY_DIR=${REMOTE_DIR}
CLOUD_DATABASE_URL=postgresql://newsc:${ENC_PASS}@127.0.0.1:15434/newsc
NEWSC_TUNNEL_LOCAL_PORT=15434
LOCAL_DATABASE_URL=${LOCAL_DATABASE_URL:-postgresql://qiubin@/newsc?host=/tmp}
EOF
  chmod 600 "$ROOT/.env.cloud.local"
  log "✓ 本机 .env.cloud.local"
else
  log "↷ 跳过 DB"
  remote "bash -s" <<EOF
set -euo pipefail
ENV=${REMOTE_DIR}/.env
if [[ -f "\$ENV" ]]; then
  sed -i "s|^WEB_PORT=.*|WEB_PORT=${WEB_PORT}|" "\$ENV" || true
  sed -i "s|^ORCH_PORT=.*|ORCH_PORT=${ORCH_PORT}|" "\$ENV" || true
  grep -q '^NEXT_PUBLIC_API_BASE=' "\$ENV" || echo "NEXT_PUBLIC_API_BASE=/api" >> "\$ENV"
  sed -i "s|^NEXT_PUBLIC_API_BASE=.*|NEXT_PUBLIC_API_BASE=/api|" "\$ENV"
  sed -i "s|^ORCH_CORS_ORIGINS=.*|ORCH_CORS_ORIGINS=http://${HOST}:${WEB_PORT}|" "\$ENV" || true
  grep -q '^ORCH_INTERNAL_URL=' "\$ENV" || echo "ORCH_INTERNAL_URL=http://127.0.0.1:${ORCH_PORT}" >> "\$ENV"
fi
EOF
fi

# 4. Python 依赖 + schema
log "▶ Python venv + init_db"
remote "bash -s" <<EOF
set -euo pipefail
export PATH="/root/.local/bin:\$PATH"
cd ${REMOTE_DIR}
set -a && source .env && set +a
uv pip install -q --python .venv -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com -e .
export PYTHONPATH="${REMOTE_DIR}:${REMOTE_DIR}/collectors/rss-CLI:${REMOTE_DIR}/collectors/youtube-CLI:${REMOTE_DIR}/collectors/bilibili-CLI:${REMOTE_DIR}/collectors/social-CLI:${REMOTE_DIR}/digest-CLI:${REMOTE_DIR}/newsc-CLI"
.venv/bin/python - <<'PY'
from pipeline.db import init_db
init_db()
print("[deploy] db schema ready")
PY
chmod +x scripts/pm2-api.sh scripts/deploy/*.sh
EOF
log "✓ schema 就绪"

# 5. Web build
if [[ "${SKIP_BUILD:-0}" != "1" ]]; then
  log "▶ npm ci && build"
  remote "bash -s" <<EOF
set -euo pipefail
cd ${REMOTE_DIR}/apps/web
set -a && source ${REMOTE_DIR}/.env && set +a
npm ci
NODE_OPTIONS=--max-old-space-size=512 NEXT_PUBLIC_API_BASE="\$NEXT_PUBLIC_API_BASE" npm run build
EOF
  log "✓ build 完成"
fi

# 6. PM2
log "▶ PM2 启动"
remote "bash -s" <<EOF
set -euo pipefail
cd ${REMOTE_DIR}
mkdir -p logs
set -a && source .env && set +a
for name in newsc-api newsc-web; do
  pm2 describe "\$name" >/dev/null 2>&1 && pm2 delete "\$name" || true
done
pm2 start ecosystem.config.cjs --update-env
pm2 save
pm2 startup systemd -u root --hp /root >/tmp/pm2-startup-newsc.out 2>&1 || true
if grep -q 'sudo env' /tmp/pm2-startup-newsc.out 2>/dev/null; then
  grep 'sudo env' /tmp/pm2-startup-newsc.out | bash || true
fi
EOF
log "✓ PM2 online"

# 7. cron
if [[ "${SKIP_SYNC_INSTALL:-0}" != "1" ]]; then
  log "▶ 安装 Linux cron"
  remote "bash ${REMOTE_DIR}/scripts/deploy/install-linux-cron.sh"
fi

# 8. 健康探测
log "▶ 健康探测"
sleep 4
remote "curl -sf -m 15 http://127.0.0.1:${ORCH_PORT}/health || true"
remote "curl -sI -m 15 http://127.0.0.1:${WEB_PORT}/ | head -5 || true"
remote "curl -sf -m 15 http://127.0.0.1:${WEB_PORT}/api/health || true"
curl -sI -m 15 "http://${HOST}:${WEB_PORT}/" | head -5 || log "⚠ 公网 ${WEB_PORT} 可能未在安全组放行"

log "════════════════════════════════════════"
log "  完成 · Web http://${HOST}:${WEB_PORT}"
log "  API  经同源 /api → 127.0.0.1:${ORCH_PORT}"
log "  远端: ${REMOTE_DIR}"
log "  PG 密码(本机): ${PG_PASS_FILE}"
log "  API token(本机): ${TOKEN_FILE}"
log "  共用: stock-pg · 库 newsc"
log "  推库: bash scripts/deploy/push-db-to-cloud.sh"
log "════════════════════════════════════════"
