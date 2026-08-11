---
name: newsc-digest-push
description: NewsC 日报 CLI — vault 只读为主；push 为兼容路径（供 OpenClaw / Hermes）
version: 1.1.0
metadata:
  cli_command: newsc-digest
  requires_install: true
  agent_safe_commands:
    - vault status
    - vault files
    - vault get
    - get
    - push
  human_required_commands: []
---

# newsc-digest

**主路径**：vault 目录 HTML（ADR-005）。**兼容**：`push` 写入 DB（ADR-004）。

## 前置条件

```bash
pip install -e .
# 或
pip install -e digest-CLI/

newsc-digest --version
```

环境变量：`NEWSC_API_URL`（默认 `http://127.0.0.1:8787`）。

## Agent 推荐命令（vault）

```bash
newsc-digest vault status --format json
newsc-digest vault files --source local-demo --format json
newsc-digest vault get --source local-demo --path demo.html --format json
newsc-digest get today --format json
```

## 兼容：push

```bash
newsc-digest push --file /tmp/digest.html --date today --source openclaw --format json
newsc-digest push --demo --format json
```

- 退出码：`0` 成功 / `2` 空内容或空列表 / `3` API 失败 / `4` 参数校验失败
- stdout：JSON；stderr：日志

## 禁止 Agent 自动调用

| 行为 | 原因 |
|------|------|
| 写入 `.env` / 改 `DATABASE_URL` | 凭证与配置属人工 |
| 绕过 CLI 直连 PostgreSQL | 写库归 orchestrator |
