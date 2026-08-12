"""云端 outbox：写入指令供 Mac Agent 消费。"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from pipeline.models import CloudOutbox, ControlSetting
from pipeline.runtime import is_cloud_runtime

logger = logging.getLogger("newsc.outbox")


def enqueue(
    db: Session,
    kind: str,
    payload: dict[str, Any] | None = None,
    *,
    origin: str = "cloud",
) -> CloudOutbox | None:
    """仅在云端运行时入队；本机直接改库无需 outbox。"""
    if not is_cloud_runtime():
        return None
    row = CloudOutbox(
        kind=kind,
        payload=dict(payload or {}),
        status="pending",
        origin=origin,
    )
    db.add(row)
    db.flush()
    logger.info("outbox_enqueue id=%s kind=%s", row.id, kind)
    return row


def upsert_control_setting(db: Session, key: str, value: dict[str, Any]) -> None:
    row = db.query(ControlSetting).filter(ControlSetting.key == key).first()
    now = datetime.now(timezone.utc)
    if row:
        row.value = dict(value)
        row.updated_at = now
    else:
        db.add(ControlSetting(key=key, value=dict(value), updated_at=now))
    db.flush()


def get_control_setting(db: Session, key: str) -> dict[str, Any] | None:
    row = db.query(ControlSetting).filter(ControlSetting.key == key).first()
    return dict(row.value) if row and isinstance(row.value, dict) else None
