# 运维备忘

## Cron（可选）

本机可用 launchd/cron 定时触发：

```bash
curl -s -X POST http://127.0.0.1:8787/pipelines/rss/run
curl -s -X POST http://127.0.0.1:8787/ai/jobs/process -H 'Content-Type: application/json' -d '{"limit":50,"include_digest":true}'
```

或由 OpenClaw cron 调用同一 HTTP 端点（业务仍经 intelligence worker 写回）。

## HTML 日报（目录直读）

在 `digest-sources.yml` 定义来源目录后，orchestrator 只读其中的 `.html`：

```bash
curl -s http://127.0.0.1:8787/digests/vault/status
curl -s 'http://127.0.0.1:8787/digests/vault/files?source=local-demo'
curl -s 'http://127.0.0.1:8787/digests/vault/file?source=local-demo&path=demo.html'
```

Web「日报」页按来源筛选并 iframe 预览。详见 [ADR-005](../ADR/005-digest-vault-sources.md)。

可选兼容：旧 CLI 推送仍可用（`newsc-digest push`），但非主路径。

## Verify 契约

`./scripts/verify.sh` 覆盖：factory、hash 去重、ingest、AI mock 写回、digest、vault HTML、ask。
