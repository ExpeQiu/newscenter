# ADR-002：本地 PG 与视频嵌入策略

- **状态**：Accepted
- **日期**：2026-08-11

## 决策

1. 使用本机 PostgreSQL 独立库 `newsc`，不写入 `openclaw` schema。
2. 视频只存可嵌入元数据（provider / id / embed_url），详情页 iframe 播放，默认不下载媒体。
3. 人工可覆盖 AI 分类，并通过 `category_locked` 防止批处理覆盖。

## 后果

- 数据本地可控；播放依赖第三方嵌入策略；无法嵌入时降级外链。
