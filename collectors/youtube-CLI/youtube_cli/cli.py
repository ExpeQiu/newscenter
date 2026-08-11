"""YouTube CLI."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4

import click

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.db import SessionLocal, init_db  # noqa: E402
from pipeline.ingest import upsert_items  # noqa: E402
from youtube_cli.collector import collect_demo  # noqa: E402


@click.group()
def main() -> None:
    """NewsC YouTube collector (embed metadata)."""


@main.command("demo")
def demo_cmd() -> None:
    init_db()
    run_id = str(uuid4())
    with SessionLocal() as db:
        stats = upsert_items(db, collect_demo(), run_id=run_id, source_name="demo-youtube")
    click.echo(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
