# 运维备忘

## Cron（推荐 `newsc` CLI）

本机可用 launchd/cron 定时触发（需已 `pip install -e .` 且 orchestrator 在跑）：

```bash
newsc --format json pipeline run rss
newsc --format json pipeline run sources   # 消费启用中的订阅源（按各源 refresh_interval 跳过未到期）
newsc --format json ai process --limit 50
newsc --format json vault status
```

订阅源可在 Web「订阅」页或 CLI 设定 `refresh_interval`（`15m`…`1d` / `manual`）。本机 LaunchAgent 每 15 分钟触发：

1. `POST /pipelines/sources/run` — 网页 / RSS / 社媒 / 视频按源级周期采集  
2. `POST /digests/vault/ingest` — 日报路径按源级周期入库（推库脚本用 `--force` 全量）

`manual` 仅在创建/改源时触发重采，定时管道会跳过。

本机一键安装（推荐）：

```bash
bash scripts/install-pipeline-sources-launchd.sh          # 每 15 分钟打管道
bash scripts/install-pipeline-sources-launchd.sh uninstall
# 日志：~/Library/Application Support/newsc/logs/pipeline-sources.log
```

> LaunchAgent 实际脚本装在 `~/Library/Application Support/newsc/`（避免 iCloud 路径被系统拒绝执行）。

兼容裸 HTTP（调试用）：

```bash
curl -s -X POST http://127.0.0.1:8787/pipelines/rss/run
curl -s -X POST http://127.0.0.1:8787/ai/jobs/process -H 'Content-Type: application/json' -d '{"limit":50,"include_digest":true}'
```

或由 OpenClaw cron 调用同一 CLI / HTTP 端点（业务仍经 intelligence worker 写回）。

## HTML 日报（目录直读）

在 `digest-sources.yml` 定义来源目录后，orchestrator 只读其中的 `.html`：

仓库默认含 `local-demo → daily/`（verify 依赖）。本机个人目录写入 `digest-sources.local.yml`（gitignore），按 id 与基线合并。

```bash
newsc --format json vault status
newsc --format json vault files --source local-demo
newsc --format json vault file --source local-demo --path demo.html
```

Web「日报」页按来源筛选并 iframe 预览。详见 [ADR-005](../ADR/005-digest-vault-sources.md)。

可选兼容：旧 CLI 推送仍可用（`newsc-digest push`），但非主路径。Vault 只读：`newsc-digest vault status`。

## 鉴权与 CORS

- 默认 CORS 白名单：`http://127.0.0.1:3000` / `http://localhost:3000`（`ORCH_CORS_ORIGINS`）
- 设置 `ORCH_API_TOKEN` 后，写接口需 `Authorization: Bearer <token>` 或 `X-API-Token`

## Verify 契约

`./scripts/verify.sh` 覆盖：factory、hash 去重、ingest、AI mock 写回、digest、vault HTML（`local-demo`）、ask、`newsc` CLI smoke。

## 混合部署（阿里云 120）

Mac 真源 + 云只读副本，对外端口 `8333`，共用 `stock-pg` 库 `newsc`。详见 [混合部署与云端运维](./混合部署与云端运维.md)。

### 日报入库（方案 2）

本机扫描 `digest-sources*.yml` 目录，HTML 写入 `digest_vault_sources` / `digest_vault_files`；推库时一并上云。云端目录不可读时自动回退读库。

```bash
# 仅入库
python -m pipeline.vault_ingest
# 或
newsc vault ingest

# 推云（默认先 ingest 再 pg_dump）
bash scripts/deploy/push-db-to-cloud.sh
```
