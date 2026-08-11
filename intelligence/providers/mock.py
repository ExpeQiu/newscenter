"""Mock provider — deterministic results for verify / offline."""
from __future__ import annotations

from intelligence.contracts import (
    AskIn,
    AskOut,
    ClassifyIn,
    ClassifyOut,
    DigestIn,
    DigestOut,
    RecommendIn,
    RecommendItem,
    RecommendOut,
    SummarizeIn,
    SummarizeOut,
)


class MockProvider:
    name = "mock"

    def summarize(self, payload: SummarizeIn) -> SummarizeOut:
        title = payload.item.title or "无标题"
        body = (payload.item.body or "")[:120]
        summary = f"【摘要】{title}：{body or '（无正文）'}…"
        return SummarizeOut(summary=summary, model_meta={"provider": self.name})

    def classify(self, payload: ClassifyIn) -> ClassifyOut:
        if payload.item.category_locked and payload.item.ai_category:
            return ClassifyOut(
                category=payload.item.ai_category,
                tags=[],
                confidence=1.0,
                skipped=True,
                model_meta={"provider": self.name, "reason": "category_locked"},
            )
        text = f"{payload.item.title} {payload.item.body}".lower()
        if any(k in text for k in ("ai", "llm", "模型", "智能")):
            cat, tags = "科技", ["AI"]
        elif any(k in text for k in ("股市", "财经", "finance", "economy")):
            cat, tags = "财经", ["市场"]
        elif payload.item.source_type in ("youtube", "bilibili"):
            cat, tags = "视频", [payload.item.source_type]
        else:
            cat, tags = "综合", ["资讯"]
        return ClassifyOut(category=cat, tags=tags, confidence=0.8, model_meta={"provider": self.name})

    def digest(self, payload: DigestIn) -> DigestOut:
        lines = [f"# 今日洞察 · {payload.digest_date}", ""]
        highlights: list[str] = []
        for i, it in enumerate(payload.items[:10], 1):
            s = it.summary or it.title or it.id
            lines.append(f"{i}. **{it.title or '无标题'}** — {s[:160]}")
            highlights.append(it.title or it.id)
        if len(payload.items) == 0:
            lines.append("_暂无条目，请先运行采集。_")
        return DigestOut(
            markdown="\n".join(lines),
            highlights=highlights,
            model_meta={"provider": self.name, "count": len(payload.items)},
        )

    def recommend(self, payload: RecommendIn) -> RecommendOut:
        starred = set(payload.user_signals.get("starred_categories") or [])
        scored: list[RecommendItem] = []
        for it in payload.candidates:
            score = 0.5
            reason = "近期内容"
            if it.ai_category and it.ai_category in starred:
                score = 0.9
                reason = f"匹配你关注的分类「{it.ai_category}」"
            elif it.summary:
                score = 0.7
                reason = "已有摘要，适合快速阅读"
            scored.append(RecommendItem(id=it.id, score=score, reason=reason))
        scored.sort(key=lambda x: x.score, reverse=True)
        return RecommendOut(items=scored[:7], model_meta={"provider": self.name})

    def ask(self, payload: AskIn) -> AskOut:
        ctx = payload.context or {}
        title = ctx.get("title") or ctx.get("item_id") or "当前内容"
        answer = (
            f"（Mock）关于「{title}」：{payload.question}\n"
            f"建议结合摘要与原文判断；真模式将由 OpenClaw 回答。"
        )
        citations = []
        if ctx.get("url"):
            citations.append(str(ctx["url"]))
        if ctx.get("item_id"):
            citations.append(f"item:{ctx['item_id']}")
        return AskOut(answer=answer, citations=citations, model_meta={"provider": self.name})
