# ADR-004：日报 HTML 经 CLI 推送

## 状态

Accepted · 2026-08-11

## 背景

OpenClaw / Hermes 可在仓外生成 HTML 日报，需要稳定写入 NewsC 展示，且与现有 intelligence 拉式 markdown digest 解耦。

## 决策

1. 新增 `digest-CLI`（命令 `newsc-digest`），仅经 HTTP 调用 `POST /digests/push`，不直连 PostgreSQL。
2. `digests` 表增加 `html`、`source`；Web 优先渲染 `html`，否则回退 `markdown`。
3. 提供 `SKILL.md` + `agent/manifest.json`（Skill 名 `newsc-digest-push`），与 Provider skill `newsc-digest` 并存。
4. 服务端对 HTML 做轻量剥离（script / 事件属性 / iframe），本机受信 Agent，暂不加 push token。

## 后果

- Agent 安装 CLI 后即可推送；orchestrator 仍为唯一写库入口。
- 同一 `digest_date` upsert，后写覆盖；`source` + `run_id` 可追溯。
- 拉式 AI job 继续写 markdown / `source=intelligence`，可与 HTML 并存。
