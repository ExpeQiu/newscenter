# ADR-003：Mock First 与 Provider 切换

- **状态**：Accepted
- **日期**：2026-08-11

## 决策

- 默认 `AI_MOCK_MODE=true`，强制 `MockProvider`，保证 `verify.sh` 不依赖 Gateway。
- 关闭 Mock 且 `AI_PROVIDER=openclaw` 时走本机 Gateway。
- Gateway 不可用时：浏览/标记仍可用；`ai_jobs` 保持 pending/failed；verify 对真模式可 skip。

## 后果

- 开发成本可控；生产切换仅改环境变量。
