# NewsC

个人化内容聚合消费平台：**每日一站，洞察全网**。

采集 → 本地 PostgreSQL(`newsc`) → 独立 `intelligence` 模块（Mock / OpenClaw）→ Next 专栏。

## 快速开始

```bash
cp .env.example .env
./scripts/start.sh
./scripts/verify.sh
```

- API：http://127.0.0.1:8787/health  
- Web：http://127.0.0.1:3000  

停止：`./scripts/stop.sh`

## Provider 切换

| 变量 | 说明 |
|------|------|
| `AI_MOCK_MODE=true` | 强制 Mock（默认，verify 必过） |
| `AI_PROVIDER=openclaw` | 且 Mock=false 时走本机 Gateway |
| `OPENCLAW_GATEWAY_URL` / `OPENCLAW_TOKEN` | Gateway 地址与鉴权 |

OpenClaw Skills 位于 [`skills/`](skills/)，可软链到 `~/.openclaw/skills/`：

```bash
ln -s "$(pwd)/skills/newsc-summarize" ~/.openclaw/skills/newsc-summarize
# classify / digest / recommend 同理
```

## HTML 日报推送（CLI）

OpenClaw / Hermes 可通过 `newsc-digest` 推送 HTML：

```bash
pip install -e .
newsc-digest push --file report.html --source hermes --format json
# 或验收
newsc-digest push --demo --format json
```

Skill 与 manifest：[`digest-CLI/`](digest-CLI/)（`newsc-digest-push`）。

## 目录

- `orchestrator/` FastAPI
- `intelligence/` AI 契约 + worker + providers
- `collectors/*-CLI` RSS / YouTube / Bilibili
- `digest-CLI/` HTML 日报推送 CLI
- `pipeline/` 模型、hash、入库
- `apps/web/` 晨报编辑台 UI
- `ADR/` 决策记录

## 演示流

设置页「采集 Demo」→「处理 AI Jobs」→ 今日页查看日报与荐读 → 详情内嵌播放视频。
