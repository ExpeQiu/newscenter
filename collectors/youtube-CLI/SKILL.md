---
name: newsc-youtube
description: NewsC YouTube 元数据采集（不下载媒体）
version: 1.0.0
metadata:
  cli_command: newsc-youtube
  agent_safe_commands: [demo, fetch]
---

# newsc-youtube

```bash
newsc-youtube demo --format json
newsc-youtube fetch --video-id jNQXAC9IVRw --format json
newsc-youtube fetch-channel --account TheValley101 --format json
# 订阅源（Cron）：newsc sources add --name 硅谷101 --type youtube --account TheValley101
#                newsc pipeline run sources
```
