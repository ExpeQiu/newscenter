"""Items / marks / tags / category / recommendations."""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from orchestrator.api.helpers import heuristic_recommendations, item_dict
from pipeline.db import get_db
from pipeline.models import Item, ItemTag, Mark, Recommendation, Tag

router = APIRouter(tags=["items"])


@router.get("/items")
def list_items(
    db: Session = Depends(get_db),
    source_type: Optional[str] = None,
    content_type: Optional[str] = None,
    category: Optional[str] = None,
    unread: Optional[bool] = None,
    starred: Optional[bool] = None,
    archived: Optional[bool] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    q = db.query(Item).order_by(Item.fetched_at.desc())
    if source_type:
        q = q.filter(Item.source_type == source_type)
    if content_type:
        q = q.filter(Item.content_type == content_type)
    if category:
        q = q.filter(Item.ai_category == category)
    items = q.offset(offset).limit(limit * 2).all()
    out = []
    for item in items:
        d = item_dict(item, db)
        m = d["marks"]
        if unread is True and m["is_read"]:
            continue
        if unread is False and not m["is_read"]:
            continue
        if starred is True and not m["is_starred"]:
            continue
        if archived is True and not m["is_archived"]:
            continue
        if archived is False and m["is_archived"]:
            continue
        out.append(d)
        if len(out) >= limit:
            break
    return {"items": out, "count": len(out)}


@router.get("/items/{item_id}")
def get_item(item_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(404, "item not found")
    return item_dict(item, db)


class MarksPatch(BaseModel):
    is_read: Optional[bool] = None
    is_starred: Optional[bool] = None
    is_archived: Optional[bool] = None
    note: Optional[str] = None


@router.patch("/items/{item_id}/marks")
def patch_marks(item_id: str, body: MarksPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(404, "item not found")
    mark = db.query(Mark).filter(Mark.item_id == item_id).first()
    if not mark:
        mark = Mark(item_id=item_id)
        db.add(mark)
    if body.is_read is not None:
        mark.is_read = body.is_read
    if body.is_starred is not None:
        mark.is_starred = body.is_starred
    if body.is_archived is not None:
        mark.is_archived = body.is_archived
    if body.note is not None:
        mark.note = body.note
    db.commit()
    db.refresh(item)
    return item_dict(item, db)


class TagsPatch(BaseModel):
    tags: list[str] = Field(default_factory=list)
    origin: str = "user"


@router.patch("/items/{item_id}/tags")
def patch_tags(item_id: str, body: TagsPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(404, "item not found")
    for it in list(item.item_tags):
        if it.origin == "user":
            db.delete(it)
    for name in body.tags:
        name = name.strip()
        if not name:
            continue
        tag = db.query(Tag).filter(Tag.name == name).first()
        if not tag:
            tag = Tag(name=name)
            db.add(tag)
            db.flush()
        db.add(ItemTag(item_id=item_id, tag_id=tag.id, origin=body.origin))
    db.commit()
    db.refresh(item)
    return item_dict(item, db)


class CategoryPatch(BaseModel):
    category: str
    lock: bool = True


@router.patch("/items/{item_id}/category")
def patch_category(item_id: str, body: CategoryPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(404, "item not found")
    item.ai_category = body.category
    item.category_locked = body.lock
    db.commit()
    db.refresh(item)
    return item_dict(item, db)


@router.get("/recommendations")
def recommendations(db: Session = Depends(get_db), limit: int = 7) -> dict[str, Any]:
    d = date.today()
    rows = (
        db.query(Recommendation)
        .filter(Recommendation.as_of == d)
        .order_by(Recommendation.score.desc())
        .limit(limit)
        .all()
    )
    items = []
    for r in rows:
        item = db.query(Item).filter(Item.id == r.item_id).first()
        if not item:
            continue
        items.append(
            {
                "score": r.score,
                "reason": r.reason,
                "item": item_dict(item, db),
            }
        )
    fallback = False
    if not items:
        items = heuristic_recommendations(db, day=d, limit=limit)
        fallback = bool(items)
    return {"as_of": d.isoformat(), "items": items, "fallback": fallback}
