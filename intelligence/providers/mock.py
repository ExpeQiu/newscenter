"""Mock provider — deterministic results for verify / offline."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

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
    RetrieveEventsIn,
    RetrieveEventsOut,
    RetrievedEvent,
    RetrievedObservation,
    RetrieveMacroIn,
    RetrieveMacroOut,
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
            f"建议结合摘要与原文判断；真模式将由 MiniMax / OpenClaw 回答。"
        )
        citations = []
        if ctx.get("url"):
            citations.append(str(ctx["url"]))
        if ctx.get("item_id"):
            citations.append(f"item:{ctx['item_id']}")
        return AskOut(answer=answer, citations=citations, model_meta={"provider": self.name})

    def retrieve_events(self, payload: RetrieveEventsIn) -> RetrieveEventsOut:
        now = datetime.now(timezone.utc)
        dim = payload.dimension
        industry = payload.industry
        entity = payload.entity
        samples: list[RetrievedEvent] = []
        if dim == "global":
            samples = [
                RetrievedEvent(
                    title="主要央行维持谨慎立场",
                    summary="多国央行会议纪要显示，通胀粘性仍是政策焦点，市场预期降息节奏放缓。",
                    occurred_at=(now - timedelta(days=1)).isoformat(),
                    source_urls=["https://example.com/mock/global-1"],
                ),
                RetrievedEvent(
                    title="全球供应链局部扰动升级",
                    summary="关键海峡航运与港口作业受阻，部分大宗商品现货溢价抬升。",
                    occurred_at=(now - timedelta(days=3)).isoformat(),
                    source_urls=["https://example.com/mock/global-2"],
                ),
            ]
        elif dim == "china":
            samples = [
                RetrievedEvent(
                    title="宏观政策组合拳落地",
                    summary="部委发布稳增长与促消费配套措施，市场关注后续执行节奏。",
                    occurred_at=(now - timedelta(days=1)).isoformat(),
                    source_urls=["https://example.com/mock/china-1"],
                ),
                RetrievedEvent(
                    title="重点行业监管口径更新",
                    summary="相关指引强调合规经营与数据安全，头部企业加速自查整改。",
                    occurred_at=(now - timedelta(days=4)).isoformat(),
                    source_urls=["https://example.com/mock/china-2"],
                ),
            ]
        elif dim == "industry":
            label = industry or "行业"
            samples = [
                RetrievedEvent(
                    title=f"{label}产业资本开支升温",
                    summary=f"多家{label}相关企业披露扩产与研发投入计划，供需预期改善。",
                    occurred_at=(now - timedelta(days=2)).isoformat(),
                    industry=industry,
                    source_urls=["https://example.com/mock/industry-1"],
                ),
                RetrievedEvent(
                    title=f"{label}标准与生态进展",
                    summary="行业联盟推进互操作标准，头部厂商发布配套工具链。",
                    occurred_at=(now - timedelta(days=5)).isoformat(),
                    industry=industry,
                    source_urls=["https://example.com/mock/industry-2"],
                ),
            ]
        else:
            name = entity or "企业"
            samples = [
                RetrievedEvent(
                    title=f"{name}发布重要业务进展",
                    summary=f"（Mock）检索「{payload.query}」：{name}公布产品/财报/合作相关更新。",
                    occurred_at=(now - timedelta(hours=18)).isoformat(),
                    industry=industry,
                    entity=entity,
                    source_urls=["https://example.com/mock/enterprise-1"],
                ),
                RetrievedEvent(
                    title=f"{name}管理层公开表态",
                    summary="对公司战略与资本开支给出最新展望，市场情绪随之波动。",
                    occurred_at=(now - timedelta(days=6)).isoformat(),
                    industry=industry,
                    entity=entity,
                    source_urls=["https://example.com/mock/enterprise-2"],
                ),
            ]
        return RetrieveEventsOut(
            events=samples,
            model_meta={"provider": self.name, "query_id": payload.query_id, "dimension": dim},
        )

    def retrieve_macro(self, payload: RetrieveMacroIn) -> RetrieveMacroOut:
        now = datetime.now(timezone.utc)
        defaults: dict[str, tuple[float, str, str]] = {
            "us.fed_funds": (4.25, "%", "目标区间上限"),
            "us.cpi.yoy": (2.8, "%", "最新公布同比"),
            "cn.gdp.yoy": (5.0, "%", "最新季度同比"),
            "cn.cpi.yoy": (0.3, "%", "最新月度同比"),
            "cn.pmi.mfg": (50.1, "", "官方制造业 PMI"),
            "ai.gpu_asp": (30000.0, "USD", "高端加速卡参考均价"),
            "ai.dram.ddr5_spot": (8.5, "USD", "DDR5 现货参考价/片或模块近似"),
            "ai.hbm.asp": (20.0, "USD", "HBM 每 GB 参考均价"),
            "ai.token.gpt4o_in": (2.5, "USD/1M", "GPT-4o 输入 Token"),
            "ai.token.claude_sonnet_in": (3.0, "USD/1M", "Claude Sonnet 输入 Token"),
            "ai.token.gemini_pro_in": (1.25, "USD/1M", "Gemini Pro 输入 Token"),
            "ai.token.deepseek_in": (0.14, "USD/1M", "DeepSeek 输入 Token"),
            "cn.m2.yoy": (7.0, "%", "广义货币 M2 同比"),
            "cn.lpr.1y": (3.1, "%", "1 年期 LPR"),
            "cn.lpr.5y": (3.6, "%", "5 年期以上 LPR"),
            "cn.social_financing.yoy": (8.2, "%", "社融存量同比"),
            "cn.rmb_loans.yoy": (7.5, "%", "人民币贷款余额同比"),
            "cn.re.price_70.yoy": (-3.5, "%", "70 城新建商品住宅价格指数同比"),
            "cn.re.sales_area.yoy": (-12.0, "%", "商品房销售面积累计同比"),
            "cn.re.starts.yoy": (-20.0, "%", "房屋新开工面积累计同比"),
            "cn.re.investment.yoy": (-9.5, "%", "房地产开发投资累计同比"),
            "energy.brent": (78.0, "USD/bbl", "布伦特原油"),
            "energy.wti": (74.0, "USD/bbl", "WTI 原油"),
            "energy.henry_hub": (2.8, "USD/MMBtu", "亨利港天然气"),
            "energy.cn_thermal_coal": (780.0, "CNY/t", "秦皇岛动力煤参考价"),
            "energy.eu_ttf": (35.0, "EUR/MWh", "欧洲 TTF 天然气"),
            "materials.lme_copper": (9500.0, "USD/t", "LME 铜"),
            "materials.lme_aluminum": (2500.0, "USD/t", "LME 铝"),
            "materials.iron_ore_62": (105.0, "USD/t", "铁矿石 62%"),
            "materials.lithium_carbonate": (75000.0, "CNY/t", "电池级碳酸锂"),
            "materials.cn_rebar": (3400.0, "CNY/t", "螺纹钢现货"),
        }
        val, unit, desc = defaults.get(
            payload.indicator_id,
            (1.0, payload.unit or "", f"Mock 观测：{payload.label or payload.indicator_id}"),
        )
        obs = [
            RetrievedObservation(
                value=val,
                value_text=f"{val}{unit}".strip(),
                observed_at=now.isoformat(),
                period_label=now.strftime("%Y-%m"),
                source_urls=[f"https://example.com/mock/macro/{payload.indicator_id}"],
            ),
            RetrievedObservation(
                value=round(val * 0.98, 4) if isinstance(val, float) else val,
                value_text=None,
                observed_at=(now - timedelta(days=30)).isoformat(),
                period_label=(now - timedelta(days=30)).strftime("%Y-%m"),
                source_urls=[],
            ),
        ]
        return RetrieveMacroOut(
            observations=obs,
            label=payload.label or payload.indicator_id,
            unit=unit or payload.unit,
            description=desc,
            model_meta={"provider": self.name, "query_id": payload.query_id, "scope": payload.scope},
        )
