# ADR-001：智能层独立模块 + Provider 插件

- **状态**：Accepted
- **日期**：2026-08-11

## 上下文

NewsC 需要摘要、分类、日报、推荐与追问能力，并希望复用本机 OpenClaw，同时保持业务与 Agent 协议解耦。

## 决策

1. 仓内独立包 `intelligence/` 拥有能力契约与 job worker；编排与 Web **不直连** OpenClaw。
2. Provider 工厂按 `AI_MOCK_MODE` / `AI_PROVIDER` 选择 `mock` 或 `openclaw`（预留 `spagent`）。
3. 业务真相在 PostgreSQL 库 `newsc`；Agent 仅经 worker 写回。

## 后果

- 可离线 `verify`（Mock First）。
- 更换内核只需新 Provider，不改 REST 与前端。
