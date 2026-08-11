# ADR-003：Mock First 与 Provider 切换

- **状态**：Accepted（2026-08-11 增补 MiniMax）
- **日期**：2026-08-11

## 决策

- 默认 `AI_MOCK_MODE=true`，强制 `MockProvider`，保证 `verify.sh` 不依赖外网。
- 关闭 Mock 后按 `AI_PROVIDER` 选择：
  - `minimax`（优先真服务）：OpenAI 兼容 Chat Completions，默认 `https://api.minimaxi.com/v1` + `MiniMax-M3`
  - `openclaw`：本机 Gateway
  - 预留 `spagent`
- 真 Provider 不可用时：默认 soft fallback 到 Mock（`model_meta.fallback=true`）；`AI_FALLBACK_STRICT=true` 则失败。

## 配置（MiniMax）

```bash
AI_MOCK_MODE=false
AI_PROVIDER=minimax
MINIMAX_API_KEY=...
# MINIMAX_BASE_URL=https://api.minimaxi.com/v1   # 国际站可用 api.minimax.io
# MINIMAX_MODEL=MiniMax-M3
```

## 后果

- 开发成本可控；生产切换仅改环境变量。
- verify 保持 Mock；真模式用设置页 / `newsc ai process` 验收。
