---
name: newsc-rss
description: NewsC RSS 采集 CLI（默认 HTTP /ingest/batch）
version: 1.0.0
metadata:
  cli_command: newsc-rss
  agent_safe_commands: [demo, fetch]
---

# newsc-rss

```bash
newsc-rss demo --format json
newsc-rss fetch --url https://example.com/feed.xml --format json
newsc-rss fetch-page --url https://stock.10jqka.com.cn/zaopan/ --name 同花顺早盘 --format json
# 订阅页「指定网页」：newsc sources add --name 同花顺早盘 --type web --url https://stock.10jqka.com.cn/zaopan/
# 开发逃生舱
newsc-rss --local-db demo --format json
```

禁止直连 PG（除非显式 `--local-db`）。
