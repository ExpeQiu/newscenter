---
name: newsc-social
description: NewsC 社媒采集（X 优先；微博/小红书后续）
version: 1.0.0
metadata:
  cli_command: newsc-social
  agent_safe_commands: [demo, fetch-x, fetch]
---

# newsc-social

```bash
newsc-social demo --format json
newsc-social fetch-x --handle Google --format json
# 订阅：newsc sources add --name Google --type social --handle Google --platform x
#       newsc pipeline run sources
```

GraphQL query id 轮换时可用环境变量：`NEWSC_X_QID_USER` / `NEWSC_X_QID_TWEETS` / `NEWSC_X_BEARER`。
