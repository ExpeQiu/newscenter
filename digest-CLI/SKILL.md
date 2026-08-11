---
name: newsc-digest-push
description: 将 HTML 日报通过 newsc-digest CLI 推送到 NewsC（供 OpenClaw / Hermes 调用）
version: 1.0.0
metadata:
  cli_command: newsc-digest
  requires_install: true
  agent_safe_commands:
    - push
    - get
  human_required_commands: []
---

# newsc-digest-push

向本机 NewsC 推送 HTML 日报。与 Provider 拉式 `newsc-digest`（markdown）并存；本 Skill 走 **CLI → HTTP `/digests/push`**。

## 前置条件

```bash
# 在 NewsC 仓根
pip install -e .
# 或仅 digest-CLI
pip install -e digest-CLI/

newsc-digest --version
# Orchestrator 已启动：http://127.0.0.1:8787/health
```

环境变量：`NEWSC_API_URL`（默认 `http://127.0.0.1:8787`）。

## Agent 推荐命令

推送 HTML 文件（agent_safe）：

```bash
newsc-digest push --file /tmp/digest.html --date today --source openclaw --format json
# Hermes 时将 --source 设为 hermes
```

从 stdin 推送：

```bash
cat report.html | newsc-digest push --stdin --source hermes --format json
```

Demo（验收 / 无文件时）：

```bash
newsc-digest push --demo --format json
```

读取今日日报：

```bash
newsc-digest get today --format json
```

- 退出码：`0` 成功 / `2` 空内容或空日报 / `3` API 失败 / `4` 参数校验失败
- stdout：JSON（`ok`, `digest_date`, `id`, `source`, `run_id`, `bytes`）
- stderr：日志

## 长任务说明

`push` / `get` 均为短请求，可同步等待；禁止用本 CLI 替代采集管道长任务。

## 禁止 Agent 自动调用

| 行为 | 原因 |
|------|------|
| 写入 `.env` / 改 `DATABASE_URL` | 凭证与配置属人工 |
| 绕过 CLI 直连 PostgreSQL | 写库归 orchestrator |

## 输出解析

stdout = JSON；stderr = 日志。成功推送后可用 `newsc-digest get today` 确认 `html` 非空。

## 安装

**OpenClaw**（软链本目录或直接 PATH 调 CLI）：

```bash
ln -s "$(pwd)/digest-CLI" ~/.openclaw/skills/newsc-digest-push
# Bash / cron
newsc-digest push --file "$HOME/reports/today.html" --source openclaw --format json
```

**Hermes**：

```bash
hermes skills install /path/to/NewsC/digest-CLI
```
