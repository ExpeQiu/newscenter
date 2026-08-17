---
name: newsc
description: NewsC 统一运维/查询 CLI（管道、AI、vault、订阅源），经 HTTP 调 orchestrator
version: 1.0.0
metadata:
  cli_command: newsc
  requires_install: true
  agent_safe_commands:
    - health
    - pipeline run
    - ai process
    - vault status
    - vault files
    - vault file
    - digest today
    - items
    - sources list
    - sources add
    - sources enable
    - sources disable
  human_required_commands:
    - sources delete
    - vault-source delete
---

# newsc

本机 NewsC 统一入口。所有写操作经 orchestrator HTTP，禁止直连 PostgreSQL。

## 前置

```bash
pip install -e .
# 或
pip install -e newsc-CLI/

newsc --version
# API: http://127.0.0.1:8787/health
```

环境变量：`NEWSC_API_URL`（默认 `http://127.0.0.1:8787`）。

## Agent 推荐命令

```bash
newsc --format json health
newsc --format json pipeline run rss
newsc --format json pipeline run sources
newsc --format json pipeline run insight --force
newsc --format json ai process --limit 50
newsc --format json vault status
newsc --format json sources list
```

退出码：`0` 成功 / `2` 空结果 / `3` API 失败 / `4` 参数错误。stdout=JSON；stderr=日志。

## 禁止

| 行为 | 原因 |
|------|------|
| 直连 DATABASE_URL / PostgreSQL | 写库归 orchestrator |
| 修改 `.env` | 人工配置 |
