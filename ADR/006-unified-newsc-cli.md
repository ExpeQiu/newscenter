# ADR-006：统一 newsc CLI（HTTP 编排层）

## 状态

Accepted · 2026-08-11

## 背景

NewsC 已有分散的 `newsc-rss` / `newsc-youtube` / `newsc-bilibili` / `newsc-digest`，运维与 Cron 仍依赖裸 `curl`。需要统一入口供 Agent / launchd 调用，并与 15CLI 标准对齐。

## 决策

1. 新增 `newsc-CLI/`，入口命令 `newsc`；仅经 HTTP 调用 orchestrator，禁止直连 PostgreSQL。
2. 专项采集 / digest CLI **保留**，`newsc` 为薄编排与查询面（health、pipeline、ai、vault、sources、items）。
3. 日报主路径仍为 vault（ADR-005）；`newsc-digest push` 为兼容路径。
4. 采集默认改为 `POST /ingest/batch`；`--local-db` 仅作开发逃生舱。
5. 每 CLI 提供 `verify.sh`、`SKILL.md`、`agent/manifest.json`；exit code：`0/2/3/4`。

## 后果

- Cron / OpenClaw 可统一调用 `newsc …`，文档不再以 curl 为主路径。
- 写库契约收敛到 orchestrator；Agent 可安全编排短 HTTP 任务。

## 15CLI 对照（附录）

| 项 | 本仓落地 |
|----|----------|
| Click + console_scripts | `newsc` / `newsc-*` |
| stdout 数据 / stderr 日志 | 默认 `--format json` |
| `--demo` / Mock | 采集 demo；`AI_MOCK_MODE` |
| exit 0/2/3/4 | 各 CLI `exit_codes.py` 或常量 |
| SKILL + manifest | `newsc-CLI/`、`digest-CLI/`、`collectors/*-CLI/` |
