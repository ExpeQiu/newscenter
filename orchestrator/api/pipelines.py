"""Pipeline run endpoints (demo + enabled sources)."""
from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from orchestrator.api.sources import run_enabled_sources
from pipeline.db import get_db
from pipeline.ingest import upsert_items

logger = logging.getLogger("newsc.orchestrator")
router = APIRouter(tags=["pipelines"])


@router.post("/pipelines/{pipeline_id}/run")
def run_pipeline(pipeline_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    run_id = str(uuid4())
    logger.info("pipeline_run id=%s run_id=%s", pipeline_id, run_id)

    if pipeline_id == "sources":
        return run_enabled_sources(db, run_id)

    if pipeline_id in ("ingest", "rss"):
        from rss_cli.collector import collect_demo

        items = collect_demo()
        stats = upsert_items(db, items, run_id=run_id, source_name="demo-rss", enqueue_ai=True)
        return {"pipeline_id": pipeline_id, **stats}

    if pipeline_id == "youtube":
        from youtube_cli.collector import collect_demo

        items = collect_demo()
        stats = upsert_items(db, items, run_id=run_id, source_name="demo-youtube", enqueue_ai=True)
        return {"pipeline_id": pipeline_id, **stats}

    if pipeline_id == "bilibili":
        from bilibili_cli.collector import collect_demo

        items = collect_demo()
        stats = upsert_items(db, items, run_id=run_id, source_name="demo-bilibili", enqueue_ai=True)
        return {"pipeline_id": pipeline_id, **stats}

    if pipeline_id == "all-demo":
        from bilibili_cli.collector import collect_demo as bili_demo
        from rss_cli.collector import collect_demo as rss_demo
        from youtube_cli.collector import collect_demo as yt_demo

        total = {"inserted": 0, "skipped": 0, "total": 0, "run_id": run_id}
        for name, fn in (("demo-rss", rss_demo), ("demo-youtube", yt_demo), ("demo-bilibili", bili_demo)):
            child = f"{run_id[:8]}-{name}-{uuid4().hex[:6]}"
            stats = upsert_items(db, fn(), run_id=child, source_name=name, enqueue_ai=True)
            total["inserted"] += stats["inserted"]
            total["skipped"] += stats["skipped"]
            total["total"] += stats["total"]
        return {"pipeline_id": pipeline_id, **total}

    raise HTTPException(404, f"unknown pipeline: {pipeline_id}")
