# 运维备忘

## Cron（可选）

本机可用 launchd/cron 定时触发：

```bash
curl -s -X POST http://127.0.0.1:8787/pipelines/rss/run
curl -s -X POST http://127.0.0.1:8787/ai/jobs/process -H 'Content-Type: application/json' -d '{"limit":50,"include_digest":true}'
```

或由 OpenClaw cron 调用同一 HTTP 端点（业务仍经 intelligence worker 写回）。

## Verify 契约

`./scripts/verify.sh` 覆盖：factory、hash 去重、ingest、AI mock 写回、digest、ask。
