"""划选笔记：栏目 CRUD + 摘录入库。"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from pipeline.db import get_db
from pipeline.models import Note, NoteColumn

logger = logging.getLogger("newsc.notes")

router = APIRouter(tags=["notes"])

DEFAULT_COLUMN_NAME = "默认"


def _column_dict(col: NoteColumn, note_count: int | None = None) -> dict[str, Any]:
    d: dict[str, Any] = {
        "id": col.id,
        "name": col.name,
        "sort_order": col.sort_order,
        "created_at": col.created_at.isoformat() if col.created_at else None,
    }
    if note_count is not None:
        d["note_count"] = note_count
    return d


def _note_dict(n: Note) -> dict[str, Any]:
    return {
        "id": n.id,
        "column_id": n.column_id,
        "quote_text": n.quote_text,
        "source_kind": n.source_kind,
        "item_id": n.item_id,
        "digest_date": n.digest_date.isoformat() if n.digest_date else None,
        "source_title": n.source_title or "",
        "source_url": n.source_url,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


def ensure_default_column(db: Session) -> NoteColumn:
    """无栏目时种子「默认」。"""
    cols = db.query(NoteColumn).order_by(NoteColumn.sort_order.asc(), NoteColumn.created_at.asc()).all()
    if cols:
        return cols[0]
    col = NoteColumn(name=DEFAULT_COLUMN_NAME, sort_order=0)
    db.add(col)
    db.commit()
    db.refresh(col)
    logger.info("note_column_seeded column_id=%s name=%s", col.id, col.name)
    return col


@router.get("/note-columns")
def list_columns(db: Session = Depends(get_db)) -> dict[str, Any]:
    ensure_default_column(db)
    cols = db.query(NoteColumn).order_by(NoteColumn.sort_order.asc(), NoteColumn.created_at.asc()).all()
    out = []
    for c in cols:
        count = db.query(Note).filter(Note.column_id == c.id).count()
        out.append(_column_dict(c, note_count=count))
    return {"columns": out, "count": len(out)}


class ColumnCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    sort_order: Optional[int] = None


@router.post("/note-columns")
def create_column(body: ColumnCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    ensure_default_column(db)
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "name required")
    exists = db.query(NoteColumn).filter(NoteColumn.name == name).first()
    if exists:
        raise HTTPException(409, "column name exists")
    max_order = db.query(NoteColumn).count()
    col = NoteColumn(name=name, sort_order=body.sort_order if body.sort_order is not None else max_order)
    db.add(col)
    db.commit()
    db.refresh(col)
    logger.info("note_column_created column_id=%s name=%s", col.id, col.name)
    return _column_dict(col, note_count=0)


class ColumnPatch(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    sort_order: Optional[int] = None


@router.patch("/note-columns/{column_id}")
def patch_column(column_id: str, body: ColumnPatch, db: Session = Depends(get_db)) -> dict[str, Any]:
    col = db.query(NoteColumn).filter(NoteColumn.id == column_id).first()
    if not col:
        raise HTTPException(404, "column not found")
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(400, "name required")
        other = db.query(NoteColumn).filter(NoteColumn.name == name, NoteColumn.id != column_id).first()
        if other:
            raise HTTPException(409, "column name exists")
        col.name = name
    if body.sort_order is not None:
        col.sort_order = body.sort_order
    db.commit()
    db.refresh(col)
    count = db.query(Note).filter(Note.column_id == col.id).count()
    logger.info("note_column_patched column_id=%s name=%s", col.id, col.name)
    return _column_dict(col, note_count=count)


@router.delete("/note-columns/{column_id}")
def delete_column(column_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    ensure_default_column(db)
    col = db.query(NoteColumn).filter(NoteColumn.id == column_id).first()
    if not col:
        raise HTTPException(404, "column not found")
    total = db.query(NoteColumn).count()
    if total <= 1:
        raise HTTPException(400, "cannot delete the last column")
    note_count = db.query(Note).filter(Note.column_id == col.id).count()
    db.delete(col)
    db.commit()
    logger.info("note_column_deleted column_id=%s notes=%s", column_id, note_count)
    return {"id": column_id, "deleted": True, "notes_removed": note_count}


@router.get("/notes")
def list_notes(
    db: Session = Depends(get_db),
    column_id: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    ensure_default_column(db)
    q = db.query(Note).order_by(Note.created_at.desc())
    if column_id:
        q = q.filter(Note.column_id == column_id)
    notes = q.offset(offset).limit(limit).all()
    return {"notes": [_note_dict(n) for n in notes], "count": len(notes)}


class NoteCreate(BaseModel):
    column_id: str
    quote_text: str = Field(..., min_length=1)
    source_kind: Literal["item", "digest"]
    item_id: Optional[str] = None
    digest_date: Optional[date] = None
    source_title: str = ""
    source_url: Optional[str] = None


@router.post("/notes")
def create_note(body: NoteCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    quote = (body.quote_text or "").strip()
    if not quote:
        raise HTTPException(400, "quote_text required")
    col = db.query(NoteColumn).filter(NoteColumn.id == body.column_id).first()
    if not col:
        raise HTTPException(404, "column not found")
    note = Note(
        column_id=body.column_id,
        quote_text=quote,
        source_kind=body.source_kind,
        item_id=body.item_id,
        digest_date=body.digest_date,
        source_title=(body.source_title or "").strip(),
        source_url=body.source_url,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    logger.info(
        "note_created note_id=%s column_id=%s source_kind=%s item_id=%s chars=%s",
        note.id,
        note.column_id,
        note.source_kind,
        note.item_id,
        len(quote),
    )
    return _note_dict(note)


@router.delete("/notes/{note_id}")
def delete_note(note_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    note = db.query(Note).filter(Note.id == note_id).first()
    if not note:
        raise HTTPException(404, "note not found")
    column_id = note.column_id
    db.delete(note)
    db.commit()
    logger.info("note_deleted note_id=%s column_id=%s", note_id, column_id)
    return {"id": note_id, "deleted": True}
