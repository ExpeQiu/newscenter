"""newsc-digest CLI — push / get HTML digests."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from uuid import uuid4

import click
import httpx
from rich.console import Console

from digest_cli import __version__
from digest_cli.client import DEMO_HTML, get_today, push_digest

console = Console(stderr=True)
logger = logging.getLogger("newsc.digest_cli")

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


@click.group()
@click.version_option(__version__, prog_name="newsc-digest")
@click.option("--verbose", is_flag=True, help="DEBUG logs on stderr")
@click.option("--api-url", envvar="NEWSC_API_URL", default=None, help="Orchestrator base URL")
@click.pass_context
def main(ctx: click.Context, verbose: bool, api_url: str | None) -> None:
    """NewsC digest push CLI for OpenClaw / Hermes agents."""
    _setup_logging(verbose)
    ctx.ensure_object(dict)
    ctx.obj["api_url"] = api_url


@main.command("push")
@click.option("--file", "file_path", type=click.Path(exists=True, dir_okay=False), default=None)
@click.option("--stdin", "use_stdin", is_flag=True, help="Read HTML from stdin")
@click.option("--demo", is_flag=True, help="Push built-in demo HTML")
@click.option("--markdown", "markdown_path", type=click.Path(exists=True, dir_okay=False), default=None)
@click.option("--date", "digest_date", default="today", help="YYYY-MM-DD or today")
@click.option(
    "--source",
    type=click.Choice(["openclaw", "hermes", "cli", "demo"], case_sensitive=False),
    default="cli",
)
@click.option("--run-id", default=None)
@click.option("--format", "fmt", type=click.Choice(["json", "text"]), default="json")
@click.pass_context
def push_cmd(
    ctx: click.Context,
    file_path: str | None,
    use_stdin: bool,
    demo: bool,
    markdown_path: str | None,
    digest_date: str,
    source: str,
    run_id: str | None,
    fmt: str,
) -> None:
    """Push HTML (and optional markdown) digest to NewsC."""
    modes = sum(bool(x) for x in (file_path, use_stdin, demo))
    if modes > 1:
        console.print("[red]use only one of --file / --stdin / --demo[/]")
        sys.exit(EXIT_VALID)
    if modes == 0 and not markdown_path:
        console.print("[red]provide --file, --stdin, --demo, or --markdown[/]")
        sys.exit(EXIT_VALID)

    html = ""
    if demo:
        html = DEMO_HTML
        source = "demo"
    elif file_path:
        html = Path(file_path).read_text(encoding="utf-8")
    elif use_stdin:
        html = sys.stdin.read()

    markdown = ""
    if markdown_path:
        markdown = Path(markdown_path).read_text(encoding="utf-8")

    if not html.strip() and not markdown.strip():
        console.print("[red]empty content[/]")
        sys.exit(EXIT_EMPTY)

    rid = run_id or str(uuid4())
    logger.info(
        "push start date=%s source=%s run_id=%s html_bytes=%s",
        digest_date,
        source,
        rid,
        len(html.encode("utf-8")),
    )

    try:
        result = push_digest(
            html=html,
            markdown=markdown,
            digest_date=digest_date,
            source=source,
            run_id=rid,
            api_url=ctx.obj.get("api_url"),
        )
    except httpx.HTTPError as exc:
        logger.error("push_api_fail err=%s", exc)
        console.print(f"[red]API failed[/] {exc}")
        sys.exit(EXIT_API)

    logger.info(
        "push done date=%s id=%s bytes=%s",
        result.get("digest_date"),
        result.get("id"),
        result.get("bytes"),
    )
    if fmt == "json":
        click.echo(json.dumps(result, ensure_ascii=False))
    else:
        console.print(
            f"[green]pushed[/] date={result.get('digest_date')} "
            f"id={result.get('id')} bytes={result.get('bytes')}"
        )
    sys.exit(EXIT_OK)


@main.command("get")
@click.argument("which", default="today", type=click.Choice(["today"]))
@click.option("--format", "fmt", type=click.Choice(["json", "text"]), default="json")
@click.pass_context
def get_cmd(ctx: click.Context, which: str, fmt: str) -> None:
    """Fetch today's digest from NewsC."""
    del which  # only today for MVP
    try:
        data = get_today(api_url=ctx.obj.get("api_url"))
    except httpx.HTTPError as exc:
        logger.error("get_api_fail err=%s", exc)
        console.print(f"[red]API failed[/] {exc}")
        sys.exit(EXIT_API)

    if data.get("empty"):
        if fmt == "json":
            click.echo(json.dumps(data, ensure_ascii=False))
        else:
            console.print("[yellow]empty digest[/]")
        sys.exit(EXIT_EMPTY)

    if fmt == "json":
        click.echo(json.dumps(data, ensure_ascii=False))
    else:
        console.print(data.get("html") or data.get("markdown") or "")
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
