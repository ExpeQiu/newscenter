"""笔记栏目与摘录 API。"""
from __future__ import annotations

from pipeline.db import SessionLocal, init_db
from pipeline.models import Note, NoteColumn
from orchestrator.api.notes import (
    ColumnCreate,
    ColumnPatch,
    NoteCreate,
    create_column,
    create_note,
    delete_column,
    delete_note,
    ensure_default_column,
    list_columns,
    list_notes,
    patch_column,
)


def setup_module() -> None:
    init_db()


def _cleanup(db) -> None:
    db.query(Note).delete()
    db.query(NoteColumn).delete()
    db.commit()


def test_seed_default_and_crud() -> None:
    db = SessionLocal()
    try:
        _cleanup(db)
        ensure_default_column(db)
        cols = list_columns(db)
        assert cols["count"] >= 1
        assert any(c["name"] == "默认" for c in cols["columns"])

        created = create_column(ColumnCreate(name="洞察摘录"), db)
        assert created["name"] == "洞察摘录"
        col_id = created["id"]

        note = create_note(
            NoteCreate(
                column_id=col_id,
                quote_text="  quote excerpt  ",
                source_kind="item",
                item_id=None,
                source_title="示例标题",
                source_url="https://example.com/a",
            ),
            db,
        )
        assert note["quote_text"] == "quote excerpt"
        assert note["source_kind"] == "item"

        listed = list_notes(db, column_id=col_id, limit=100, offset=0)
        assert listed["count"] == 1

        patched = patch_column(col_id, ColumnPatch(name="洞察·改名"), db)
        assert patched["name"] == "洞察·改名"
        assert patched["note_count"] == 1

        deleted_note = delete_note(note["id"], db)
        assert deleted_note["deleted"] is True

        # 再建一条以便测栏目级联删除
        n2 = create_note(
            NoteCreate(
                column_id=col_id,
                quote_text="日报要点",
                source_kind="digest",
                source_title="今日洞察",
            ),
            db,
        )
        assert n2["id"]
        deleted_col = delete_column(col_id, db)
        assert deleted_col["deleted"] is True
        assert deleted_col["notes_removed"] == 1

        # 至少保留默认栏目
        left = list_columns(db)
        assert left["count"] >= 1
    finally:
        _cleanup(db)
        db.close()


def test_cannot_delete_last_column() -> None:
    db = SessionLocal()
    try:
        _cleanup(db)
        col = ensure_default_column(db)
        try:
            delete_column(col.id, db)
            assert False, "expected HTTPException"
        except Exception as e:  # noqa: BLE001
            from fastapi import HTTPException

            assert isinstance(e, HTTPException)
            assert e.status_code == 400
    finally:
        _cleanup(db)
        db.close()
