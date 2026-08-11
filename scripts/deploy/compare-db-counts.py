#!/usr/bin/env python3
"""对账本机与云端 newsc 业务表行数。"""
from __future__ import annotations

import os
import sys

import psycopg


TABLES = (
    "items",
    "sources",
    "tags",
    "item_tags",
    "marks",
    "ai_jobs",
    "digests",
    "digest_vault_sources",
    "digest_vault_files",
    "pipeline_runs",
)


def normalize_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def counts(url: str) -> dict[str, int]:
    out: dict[str, int] = {}
    with psycopg.connect(normalize_url(url)) as conn:
        with conn.cursor() as cur:
            for t in TABLES:
                cur.execute(
                    """
                    SELECT EXISTS (
                      SELECT 1 FROM information_schema.tables
                      WHERE table_schema = 'public' AND table_name = %s
                    )
                    """,
                    (t,),
                )
                if not cur.fetchone()[0]:
                    out[t] = -1
                    continue
                cur.execute(f'SELECT count(*) FROM "{t}"')  # noqa: S608
                out[t] = int(cur.fetchone()[0])
    return out


def main() -> int:
    local = os.environ.get("LOCAL_URL") or os.environ.get("LOCAL_DATABASE_URL")
    cloud = os.environ.get("CLOUD_URL") or os.environ.get("CLOUD_DATABASE_URL")
    if not local or not cloud:
        print("需要 LOCAL_URL / CLOUD_URL", file=sys.stderr)
        return 2
    lc = counts(local)
    cc = counts(cloud)
    ok = True
    print(f"{'table':<20} {'local':>10} {'cloud':>10}")
    for t in TABLES:
        a, b = lc.get(t, -1), cc.get(t, -1)
        mark = "✓" if a == b else "✗"
        if a != b:
            ok = False
        print(f"{t:<20} {a:>10} {b:>10} {mark}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
