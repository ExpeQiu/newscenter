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

## HTML 日报（目录直读）

在 [`digest-sources.yml`](digest-sources.yml) 定义来源目录，Web「日报」页直接读取其中的 HTML（参考 AgentCenter 输出物）：

```bash
curl -s http://127.0.0.1:8787/digests/vault/status | python -m json.tool
```

可选兼容：`digest-CLI/` 仍可 `newsc-digest push` 写入库，但非主路径；推荐 `newsc vault *` / `newsc-digest vault *`。见 [ADR-005](ADR/005-digest-vault-sources.md)、[ADR-006](ADR/006-unified-newsc-cli.md)。

## 统一 CLI

```bash
pip install -e .
newsc health
newsc pipeline run rss
newsc ai process --limit 20
newsc vault status
newsc sources list
```

详见 [ADR-006](ADR/006-unified-newsc-cli.md)、[guide/运维与Cron.md](guide/运维与Cron.md)。

## 目录

- `orchestrator/` FastAPI
- `intelligence/` AI 契约 + worker + providers
- `newsc-CLI/` 统一运维入口 `newsc`
- `collectors/*-CLI` RSS / YouTube / Bilibili
- `digest-sources.yml` / `daily/` 日报来源与本地 Demo HTML
- `digest-CLI/` vault 只读 + 兼容 HTML 推送
- `pipeline/` 模型、hash、入库、digest_vault
- `apps/web/` 晨报编辑台 UI
- `ADR/` 决策记录

## 演示流

设置页「采集 Demo」→「处理 AI Jobs」→ 今日页查看洞察与荐读 →「日报」页浏览目录 HTML。
