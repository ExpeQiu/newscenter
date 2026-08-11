# 运维备忘

## Cron（推荐 `newsc` CLI）

本机可用 launchd/cron 定时触发（需已 `pip install -e .` 且 orchestrator 在跑）：

```bash
newsc --format json pipeline run rss
newsc --format json pipeline run sources   # 消费启用中的订阅源
newsc --format json ai process --limit 50
newsc --format json vault status
```

兼容裸 HTTP（调试用）：

```bash
curl -s -X POST http://127.0.0.1:8787/pipelines/rss/run
curl -s -X POST http://127.0.0.1:8787/ai/jobs/process -H 'Content-Type: application/json' -d '{"limit":50,"include_digest":true}'
```

或由 OpenClaw cron 调用同一 CLI / HTTP 端点（业务仍经 intelligence worker 写回）。

## HTML 日报（目录直读）

在 `digest-sources.yml` 定义来源目录后，orchestrator 只读其中的 `.html`：

```bash
newsc --format json vault status
newsc --format json vault files --source local-demo
newsc --format json vault file --source local-demo --path demo.html
```

Web「日报」页按来源筛选并 iframe 预览。详见 [ADR-005](../ADR/005-digest-vault-sources.md)。

可选兼容：旧 CLI 推送仍可用（`newsc-digest push`），但非主路径。Vault 只读：`newsc-digest vault status`。

## Verify 契约

`./scripts/verify.sh` 覆盖：factory、hash 去重、ingest、AI mock 写回、digest、vault HTML、ask、`newsc` CLI smoke。
