---
name: newsc-bilibili
description: NewsC Bilibili 元数据采集（不下载媒体）
version: 1.0.0
metadata:
  cli_command: newsc-bilibili
  agent_safe_commands: [demo, fetch]
---

# newsc-bilibili

```bash
newsc-bilibili demo --format json
newsc-bilibili fetch --bvid BV1GJ411x7h7 --format json
newsc-bilibili fetch-space --account 249035054 --format json
# 订阅源：newsc sources add --name 大家好我是何同学 --type bilibili --account 249035054
#         newsc pipeline run sources
```
