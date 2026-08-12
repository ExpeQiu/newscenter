#!/usr/bin/env python3
"""CLI：扫描日报目录写入 PostgreSQL。用法: python -m pipeline.vault_ingest [--force]"""
from __future__ import annotations

import argparse
import json
import logging
import sys

from pipeline.db import SessionLocal, init_db
from pipeline.vault_store import sync_vault_to_db


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="日报 vault 目录 → DB")
    p.add_argument(
        "--force",
        action="store_true",
        help="忽略 refresh_interval，强制扫描全部启用源",
    )
    args = p.parse_args(argv)
    init_db()
    db = SessionLocal()
    try:
        result = sync_vault_to_db(db, force=args.force)
    finally:
        db.close()
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
