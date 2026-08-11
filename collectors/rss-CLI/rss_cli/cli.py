"""RSS CLI — newsc-rss (HTTP ingest default; --local-db escape hatch)."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from uuid import uuid4

import click
import httpx
from rich.console import Console

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
RSS_ROOT = Path(__file__).resolve().parents[1]
if str(RSS_ROOT) not in sys.path:
    sys.path.insert(0, str(RSS_ROOT))

from pipeline.remote_ingest import ingest_batch_http  # noqa: E402
from rss_cli.collector import collect_demo, collect_feed, collect_page  # noqa: E402

console = Console(stderr=True)
logger = logging.getLogger("newsc.rss_cli")

EXIT_OK = 0
EXIT_EMPTY = 2
EXIT_API = 3
EXIT_VALID = 4


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )


def _persist(items, *, source_name: str, local_db: bool, api_url: str | None, run_id: str):
    if not items:
        return {"run_id": run_id, "inserted": 0, "skipped": 0, "total": 0}
    if local_db:
        from pipeline.db import SessionLocal, init_db
        from pipeline.ingest import upsert_items

        init_db()
        with SessionLocal() as db:
            return upsert_items(db, items, run_id=run_id, source_name=source_name)
    return ingest_batch_http(
        items, source_name=source_name, run_id=run_id, api_url=api_url
    )


@click.group()
@click.version_option("0.1.0", prog_name="newsc-rss")
@click.option("--verbose", is_flag=True)
@click.option("--api-url", envvar="NEWSC_API_URL", default=None)
@click.option("--local-db", is_flag=True, help="Direct PG upsert (dev only)")
@click.pass_context
def main(ctx: click.Context, verbose: bool, api_url: str | None, local_db: bool) -> None:
    """NewsC RSS collector."""
    _setup_logging(verbose)
    ctx.ensure_object(dict)
    ctx.obj["api_url"] = api_url
    ctx.obj["local_db"] = local_db


@main.command("demo")
@click.option("--format", "fmt", type=click.Choice(["json", "text"]), default="json")
@click.pass_context
def demo_cmd(ctx: click.Context, fmt: str) -> None:
    """Ingest demo RSS items."""
    run_id = str(uuid4())
    items = collect_demo()
    try:
        stats = _persist(
            items,
            source_name="demo-rss",
            local_db=ctx.obj["local_db"],
            api_url=ctx.obj.get("api_url"),
            run_id=run_id,
        )
    except httpx.HTTPError as exc:
        logger.error("demo_fail err=%s", exc)
        console.print(f"[red]API failed[/] {exc}")
        sys.exit(EXIT_API)
    if fmt == "json":
        click.echo(json.dumps(stats, ensure_ascii=False))
    else:
        console.print(
            f"[green]demo ingest[/] run_id={stats['run_id']} "
            f"inserted={stats['inserted']} skipped={stats['skipped']}"
        )
    sys.exit(EXIT_OK)


@main.command("fetch")
@click.option("--url", required=True, help="RSS/Atom feed URL")
@click.option("--name", default="rss-feed", help="Source name")
@click.option("--format", "fmt", type=click.Choice(["json", "text"]), default="json")
@click.pass_context
def fetch_cmd(ctx: click.Context, url: str, name: str, fmt: str) -> None:
    """Fetch feed and ingest via HTTP (or --local-db)."""
    run_id = str(uuid4())
    try:
        items = collect_feed(url)
    except Exception as exc:  # noqa: BLE001
        logger.error("fetch_fail err=%s", exc)
        console.print(f"[red]collect failed[/] {exc}")
        sys.exit(3)
    if not items:
        click.echo(json.dumps({"run_id": run_id, "inserted": 0, "skipped": 0, "total": 0}))
        sys.exit(EXIT_EMPTY)
    try:
        stats = _persist(
            items,
            source_name=name,
            local_db=ctx.obj["local_db"],
            api_url=ctx.obj.get("api_url"),
            run_id=run_id,
        )
    except httpx.HTTPError as exc:
        logger.error("ingest_fail err=%s", exc)
        console.print(f"[red]API failed[/] {exc}")
        sys.exit(EXIT_API)
    if fmt == "json":
        click.echo(json.dumps(stats, ensure_ascii=False))
    else:
        console.print(stats)
    sys.exit(EXIT_OK)


@main.command("fetch-page")
@click.option("--url", required=True, help="Web page URL")
@click.option("--name", default="web-page", help="Source name")
@click.option("--format", "fmt", type=click.Choice(["json", "text"]), default="json")
@click.pass_context
def fetch_page_cmd(ctx: click.Context, url: str, name: str, fmt: str) -> None:
    """Fetch HTML page text and ingest via HTTP (or --local-db)."""
    run_id = str(uuid4())
    try:
        items = collect_page(url, source_label=name)
    except Exception as exc:  # noqa: BLE001
        logger.error("fetch_page_fail err=%s", exc)
        console.print(f"[red]collect failed[/] {exc}")
        sys.exit(EXIT_API)
    if not items:
        click.echo(json.dumps({"run_id": run_id, "inserted": 0, "skipped": 0, "total": 0}))
        sys.exit(EXIT_EMPTY)
    try:
        stats = _persist(
            items,
            source_name=name,
            local_db=ctx.obj["local_db"],
            api_url=ctx.obj.get("api_url"),
            run_id=run_id,
        )
    except httpx.HTTPError as exc:
        logger.error("ingest_fail err=%s", exc)
        console.print(f"[red]API failed[/] {exc}")
        sys.exit(EXIT_API)
    if fmt == "json":
        click.echo(json.dumps(stats, ensure_ascii=False))
    else:
        console.print(stats)
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
