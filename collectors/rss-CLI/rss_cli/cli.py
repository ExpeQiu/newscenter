"""RSS CLI — newsc-rss."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from uuid import uuid4

import click
from rich.console import Console

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
RSS_ROOT = Path(__file__).resolve().parents[1]
if str(RSS_ROOT) not in sys.path:
    sys.path.insert(0, str(RSS_ROOT))

from pipeline.db import SessionLocal, init_db  # noqa: E402
from pipeline.ingest import upsert_items  # noqa: E402
from rss_cli.collector import collect_demo, collect_feed  # noqa: E402

console = Console(stderr=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


@click.group()
def main() -> None:
    """NewsC RSS collector."""


@main.command("demo")
@click.option("--format", "fmt", type=click.Choice(["json", "text"]), default="text")
def demo_cmd(fmt: str) -> None:
    """Ingest demo RSS items (offline)."""
    init_db()
    run_id = str(uuid4())
    items = collect_demo()
    with SessionLocal() as db:
        stats = upsert_items(db, items, run_id=run_id, source_name="demo-rss")
    if fmt == "json":
        click.echo(json.dumps(stats, ensure_ascii=False))
    else:
        console.print(f"[green]demo ingest[/] run_id={stats['run_id']} inserted={stats['inserted']} skipped={stats['skipped']}")


@main.command("fetch")
@click.option("--url", required=True, help="RSS/Atom feed URL")
@click.option("--name", default="rss-feed", help="Source name")
def fetch_cmd(url: str, name: str) -> None:
    init_db()
    run_id = str(uuid4())
    items = collect_feed(url)
    with SessionLocal() as db:
        stats = upsert_items(db, items, run_id=run_id, source_name=name)
    click.echo(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
