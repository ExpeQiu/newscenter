# NewsC CLI 一页对照（15CLI）

> 细节见 [ADR-006](../ADR/006-unified-newsc-cli.md)。

| 命令 | 职责 | 写库路径 |
|------|------|----------|
| `newsc` | 运维/查询/订阅/vault | 仅 HTTP → orchestrator |
| `newsc-rss` / `youtube` / `bilibili` / `social` | 专项采集 | 默认 `POST /ingest/batch`；`--local-db` 开发 |
| `newsc-digest` | vault 只读 + push 兼容 | HTTP |

## 约定

- stdout = 数据（默认 JSON）；stderr = 日志
- exit：`0` 成功 / `2` 空 / `3` API / `4` 校验
- 每包：`verify.sh`、`SKILL.md`、`agent/manifest.json`
- Cron 主路径：`newsc pipeline run …` / `newsc ai process`

## 快速验收

```bash
newsc health && newsc --format json vault status && newsc --format json pipeline run sources
newsc-digest vault status
newsc-rss --local-db demo
```
