"""Shared helpers for orchestrator route modules."""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from pipeline.digest_vault import DigestVaultError
from pipeline.models import Item, Mark

logger = logging.getLogger("newsc.orchestrator")


def raise_vault(exc: DigestVaultError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


def _local_tz():
    return datetime.now().astimezone().tzinfo or timezone.utc


def _as_aware(dt: datetime | float | int | None) -> datetime | None:
    if dt is None:
        return None
    if isinstance(dt, (int, float)):
        return datetime.fromtimestamp(float(dt), tz=_local_tz())
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            # DB 无时区时按本地时区理解（与 date.today() 对齐）
            return dt.replace(tzinfo=_local_tz())
        return dt
    return None


def item_event_at(item: Item) -> datetime | None:
    """条目展示时效：优先较新的 published_at / fetched_at。"""
    pub = _as_aware(item.published_at)
    fetch = _as_aware(item.fetched_at)
    if pub and fetch:
        return pub if pub >= fetch else fetch
    return pub or fetch


def item_in_today_window(
    item: Item,
    *,
    day: date,
    now: datetime | None = None,
) -> bool:
    """published_at 或 fetched_at 任一落在当日/24h 即算今日内容。"""
    now_a = _as_aware(now) or datetime.now(tz=_local_tz())
    for dt in (_as_aware(item.published_at), _as_aware(item.fetched_at)):
        if is_in_today_window(dt, day=day, now=now_a):
            return True
    return False


def is_in_today_window(
    dt: datetime | float | int | None,
    *,
    day: date,
    now: datetime | None = None,
) -> bool:
    """本地日历「当日」00:00 起，或滚动近 24 小时（取并集，凌晨读报仍能看到昨夜）。"""
    u = _as_aware(dt)
    if u is None:
        return False
    now_a = _as_aware(now) or datetime.now(tz=_local_tz())
    local = _local_tz()
    day_start = datetime(day.year, day.month, day.day, tzinfo=local)
    if u >= day_start:
        return True
    if u >= now_a - timedelta(hours=24):
        return True
    return False


def filter_items_today(
    items: list[Item],
    *,
    day: date,
    now: datetime | None = None,
) -> list[Item]:
    """优先日历当日；若当日为空，再退到近 24 小时。"""
    now_a = _as_aware(now) or datetime.now(tz=_local_tz())
    local = _local_tz()
    windowed = [it for it in items if item_in_today_window(it, day=day, now=now_a)]

    def _on_calendar(it: Item) -> bool:
        for dt in (_as_aware(it.published_at), _as_aware(it.fetched_at)):
            if dt and dt.astimezone(local).date() == day:
                return True
        return False

    def _sort_key(it: Item) -> tuple[int, float]:
        ev = item_event_at(it) or datetime.min.replace(tzinfo=timezone.utc)
        return (0 if _on_calendar(it) else 1, -ev.timestamp())

    calendar = [it for it in windowed if _on_calendar(it)]
    chosen = calendar if calendar else windowed
    chosen.sort(key=_sort_key)
    return chosen


def filter_vault_today(
    entries: list[Any],
    *,
    day: date,
    now: datetime | None = None,
) -> list[Any]:
    """目录日报：优先 path 含当日；否则 mtime 落在窗口。有当日则只留当日。"""
    now_a = _as_aware(now) or datetime.now(tz=_local_tz())
    day_token = day.isoformat()
    windowed: list[Any] = []
    for e in entries:
        mtime = _as_aware(getattr(e, "mtime", None))
        path = str(getattr(e, "path", "") or "")
        name = str(getattr(e, "name", "") or "")
        if day_token in path or day_token in name:
            windowed.append(e)
            continue
        if is_in_today_window(mtime, day=day, now=now_a):
            windowed.append(e)
    calendar = [e for e in windowed if day_token in str(getattr(e, "path", "")) or day_token in str(getattr(e, "name", ""))]
    chosen = calendar if calendar else windowed
    chosen.sort(key=lambda e: (0 if day_token in str(getattr(e, "path", "")) else 1))
    return chosen


def load_today_items(
    db: Session,
    *,
    day: date,
    limit: int = 40,
) -> list[Item]:
    """拉取候选后按「当日 00:00 / 近 24h」过滤，当日排前。"""
    pool = db.query(Item).order_by(Item.fetched_at.desc()).limit(max(limit * 3, 80)).all()
    today = filter_items_today(pool, day=day)
    logger.info(
        "load_today_items day=%s pool=%d today=%d",
        day.isoformat(),
        len(pool),
        len(today),
    )
    return today[: max(1, min(int(limit), 80))] if today else []


def synthesize_today_markdown(
    items: list[Item],
    *,
    day: date,
    vault_entries: list[Any] | None = None,
) -> tuple[str, list[str]]:
    """无 AI 日报时，由当日/24h 内条目（+ 目录日报清单）拼出高度总结 Markdown。

    不输出「今日洞察」标题与条数说明（页面 section 已有标题，避免重复）。
    """
    lines: list[str] = []
    highlights: list[str] = []
    vault_entries = vault_entries or []

    by_cat: dict[str, list[Item]] = defaultdict(list)
    for it in items:
        by_cat[it.ai_category or "综合"].append(it)

    if items:
        for cat, group in by_cat.items():
            lines.append(f"## {cat}")
            lines.append("")
            for it in group[:12]:
                title = (it.title or "无标题").strip()
                snippet = (it.summary or it.body or "").strip().replace("\n", " ")
                if len(snippet) > 140:
                    snippet = snippet[:140] + "…"
                if snippet:
                    lines.append(f"- **{title}** — {snippet}")
                else:
                    lines.append(f"- **{title}**")
                if title and title not in highlights:
                    highlights.append(title)
            lines.append("")
    else:
        lines.append("_今日（含近 24 小时）暂无采集条目。可先在设置中跑采集与 AI 处理。_")
        lines.append("")

    if vault_entries:
        day_token = day.isoformat()
        vault_day = [
            e
            for e in vault_entries
            if day_token in str(getattr(e, "path", "") or "")
            or day_token in str(getattr(e, "name", "") or "")
        ]
        heading = "目录日报" if vault_day else "目录日报（近 24 小时）"
        lines.append(f"## {heading}")
        lines.append("")
        for e in vault_entries[:8]:
            label = getattr(e, "source_label", None) or getattr(e, "source_id", "") or "日报"
            path = getattr(e, "path", "") or ""
            lines.append(f"- {label} · `{path}`")
        lines.append("")

    return ("\n".join(lines).strip() + "\n") if lines else "", highlights[:12]



def heuristic_recommendations(
    db: Session,
    *,
    day: date,
    limit: int = 7,
) -> list[dict[str, Any]]:
    """无 AI 荐读记录时，仅用当日/24h 条目按摘要/星标分类启发式打分。"""
    starred_cats: set[str] = set()
    for m in db.query(Mark).filter(Mark.is_starred.is_(True)).all():
        it = db.query(Item).filter(Item.id == m.item_id).first()
        if it and it.ai_category:
            starred_cats.add(it.ai_category)

    candidates = load_today_items(db, day=day, limit=40)
    scored: list[tuple[float, str, Item]] = []
    for it in candidates:
        score = 0.45
        reason = "当日内容"
        if it.ai_category and it.ai_category in starred_cats:
            score = 0.9
            reason = f"匹配你关注的分类「{it.ai_category}」"
        elif (it.summary or "").strip():
            score = 0.72
            reason = "已有摘要，适合快速阅读"
        elif it.ai_category:
            score = 0.55
            reason = f"分类「{it.ai_category}」"
        scored.append((score, reason, it))

    scored.sort(key=lambda x: x[0], reverse=True)
    out: list[dict[str, Any]] = []
    for score, reason, it in scored[: max(1, min(int(limit), 20))]:
        out.append({"score": score, "reason": reason, "item": item_dict(it, db)})
    logger.info(
        "recommendations heuristic fallback as_of=%s count=%d starred_cats=%s",
        day.isoformat(),
        len(out),
        sorted(starred_cats),
    )
    return out


def item_meta(raw: dict[str, Any] | None) -> dict[str, Any]:
    """从采集 raw 抽出列表/详情可展示字段（白名单，不整包透出）。"""
    if not isinstance(raw, dict) or not raw:
        return {}
    meta: dict[str, Any] = {}

    def _take(out: str, *keys: str) -> None:
        if out in meta:
            return
        for key in keys:
            if key not in raw:
                continue
            val = raw[key]
            if val is None or val == "" or val == "--":
                continue
            meta[out] = val
            return

    _take("play", "play", "view_count", "views")
    _take("duration", "length", "duration")
    _take("author", "up_name", "channel_title", "author")
    _take("comment", "comment", "comments")
    _take("danmaku", "video_review", "danmaku")
    return meta


def item_dict(item: Item, db: Session) -> dict[str, Any]:
    mark = item.marks
    tags = []
    for it in item.item_tags:
        if it.tag:
            tags.append({"name": it.tag.name, "origin": it.origin})
    return {
        "id": item.id,
        "source_type": item.source_type,
        "content_type": getattr(item, "content_type", None) or "news",
        "url": item.url,
        "title": item.title,
        "body": item.body,
        "summary": item.summary,
        "content_hash": item.content_hash,
        "embed_provider": item.embed_provider,
        "embed_id": item.embed_id,
        "embed_url": item.embed_url,
        "thumbnail_url": item.thumbnail_url,
        "ai_category": item.ai_category,
        "category_locked": item.category_locked,
        "published_at": item.published_at.isoformat() if item.published_at else None,
        "fetched_at": item.fetched_at.isoformat() if item.fetched_at else None,
        "meta": item_meta(getattr(item, "raw", None)),
        "marks": {
            "is_read": mark.is_read if mark else False,
            "is_starred": mark.is_starred if mark else False,
            "is_archived": mark.is_archived if mark else False,
            "note": mark.note if mark else None,
        },
        "tags": tags,
    }
