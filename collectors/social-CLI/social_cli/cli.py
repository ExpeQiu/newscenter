"""Social CLI — newsc-social (X first)."""
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
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.remote_ingest import ingest_batch_http  # noqa: E402
from social_cli.collector import collect_by_social, collect_demo, collect_x_user  # noqa: E402

console = Console(stderr=True)
logger = logging.getLogger("newsc.social_cli")

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
@click.version_option("0.1.0", prog_name="newsc-social")
@click.option("--verbose", is_flag=True)
@click.option("--api-url", envvar="NEWSC_API_URL", default=None)
@click.option("--local-db", is_flag=True, help="Direct PG upsert (dev only)")
@click.pass_context
def main(ctx: click.Context, verbose: bool, api_url: str | None, local_db: bool) -> None:
    """NewsC social collector (X / Twitter first)."""
    _setup_logging(verbose)
    ctx.ensure_object(dict)
    ctx.obj["api_url"] = api_url
    ctx.obj["local_db"] = local_db


@main.command("demo")
@click.option("--format", "fmt", type=click.Choice(["json", "text"]), default="json")
@click.pass_context
def demo_cmd(ctx: click.Context, fmt: str) -> None:
    run_id = str(uuid4())
    try:
        stats = _persist(
            collect_demo(),
            source_name="demo-social",
            local_db=ctx.obj["local_db"],
            api_url=ctx.obj.get("api_url"),
            run_id=run_id,
        )
    except httpx.HTTPError as exc:
        logger.error("demo_fail err=%s", exc)
        console.print(f"[red]API failed[/] {exc}")
        sys.exit(EXIT_API)
    click.echo(json.dumps(stats, ensure_ascii=False) if fmt == "json" else stats)
    sys.exit(EXIT_OK)


@main.command("fetch-x")
@click.option("--handle", required=True, help="@handle / x.com URL")
@click.option("--name", default=None, help="Source label for ingest")
@click.option("--limit", default=20, show_default=True)
@click.option("--format", "fmt", type=click.Choice(["json", "text"]), default="json")
@click.pass_context
def fetch_x_cmd(
    ctx: click.Context, handle: str, name: str | None, limit: int, fmt: str
) -> None:
    """Fetch recent posts for an X account and ingest."""
    run_id = str(uuid4())
    label = name or handle.strip().lstrip("@") or "x-user"
    try:
        items = collect_x_user(handle, source_label=label, limit=limit)
    except ValueError as exc:
        console.print(f"[red]{exc}[/]")
        sys.exit(EXIT_VALID)
    except Exception as exc:  # noqa: BLE001
        logger.error("fetch_x_fail err=%s", exc)
        console.print(f"[red]collect failed[/] {exc}")
        sys.exit(EXIT_API)
    if not items:
        console.print("[yellow]empty[/]")
        sys.exit(EXIT_EMPTY)
    try:
        stats = _persist(
            items,
            source_name=label,
            local_db=ctx.obj["local_db"],
            api_url=ctx.obj.get("api_url"),
            run_id=run_id,
        )
    except httpx.HTTPError as exc:
        logger.error("ingest_fail err=%s", exc)
        console.print(f"[red]API failed[/] {exc}")
        sys.exit(EXIT_API)
    click.echo(json.dumps(stats, ensure_ascii=False) if fmt == "json" else stats)
    sys.exit(EXIT_OK)


@main.command("fetch")
@click.option("--platform", default="x", show_default=True)
@click.option("--handle", required=True)
@click.option("--name", default=None)
@click.option("--limit", default=20, show_default=True)
@click.option("--format", "fmt", type=click.Choice(["json", "text"]), default="json")
@click.pass_context
def fetch_cmd(
    ctx: click.Context,
    platform: str,
    handle: str,
    name: str | None,
    limit: int,
    fmt: str,
) -> None:
    """Generic social fetch (X implemented; others no-op empty)."""
    run_id = str(uuid4())
    label = name or handle.strip().lstrip("@") or "social"
    try:
        items = collect_by_social(
            platform=platform, handle=handle, source_label=label, limit=limit
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/]")
        sys.exit(EXIT_VALID)
    except Exception as exc:  # noqa: BLE001
        logger.error("fetch_fail err=%s", exc)
        console.print(f"[red]collect failed[/] {exc}")
        sys.exit(EXIT_API)
    if not items:
        console.print("[yellow]empty / unsupported platform[/]")
        sys.exit(EXIT_EMPTY)
    try:
        stats = _persist(
            items,
            source_name=label,
            local_db=ctx.obj["local_db"],
            api_url=ctx.obj.get("api_url"),
            run_id=run_id,
        )
    except httpx.HTTPError as exc:
        logger.error("ingest_fail err=%s", exc)
        console.print(f"[red]API failed[/] {exc}")
        sys.exit(EXIT_API)
    click.echo(json.dumps(stats, ensure_ascii=False) if fmt == "json" else stats)
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
