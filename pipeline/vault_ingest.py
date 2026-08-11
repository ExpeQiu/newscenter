#!/usr/bin/env python3
"""CLI：扫描日报目录写入 PostgreSQL。用法: python -m pipeline.vault_ingest"""
from __future__ import annotations

import json
import logging
import sys

from pipeline.db import SessionLocal, init_db
from pipeline.vault_store import sync_vault_to_db


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    init_db()
    db = SessionLocal()
    try:
        result = sync_vault_to_db(db)
    finally:
        db.close()
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
