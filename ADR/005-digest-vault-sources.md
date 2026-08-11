# ADR-005：日报 HTML 按来源目录直读

## 状态

Accepted · 2026-08-11

## 背景

原先 HTML 日报依赖 `digest-CLI` → `POST /digests/push` 写入 PostgreSQL，与 OpenClaw/Hermes 已落盘的 HTML 产物重复搬运。AgentCenter「输出物」已证明：定义 vault/来源范围后只读文件系统更直接。

## 决策

1. 以 `digest-sources.yml` 定义来源（`id` / `label` / `path`），orchestrator 只读扫描 `.html`/`.htm`。
2. 新增 `GET /digests/vault/status|files|file`；Web「日报」页按来源列表 + iframe 沙箱预览。
3. `/digests/today` 优先取 vault 最新 HTML；DB markdown（AI 洞察）与旧 CLI push 仍保留兼容。
4. 路径解析禁止 `..` 逃逸；展示前继续 `sanitize_digest_html`。

## 后果

- 新增/调整日报只需改 YAML 路径或往目录丢 HTML，无需再 push。
- 来源路径依赖本机可读目录（如 Obsidian expe）；不可读时该来源标记 `readable=false`。
- CLI push 降为可选兼容路径，非日报主路径。
