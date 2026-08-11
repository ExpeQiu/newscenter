"""newsc — unified NewsC ops / query CLI (HTTP-only)."""
from __future__ import annotations

import json
import logging
import sys
from typing import Any

import click
import httpx
from rich.console import Console

from newsc_cli import __version__
from newsc_cli.client import NewsCClient
from newsc_cli.exit_codes import EXIT_API, EXIT_EMPTY, EXIT_OK, EXIT_VALID

console = Console(stderr=True)
logger = logging.getLogger("newsc.cli")

PIPELINE_IDS = ("rss", "youtube", "bilibili", "all-demo", "sources")
SOURCE_TYPES = ("web", "rss", "social", "bilibili", "youtube")


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )


def _emit(data: Any, fmt: str) -> None:
    if fmt == "json":
        click.echo(json.dumps(data, ensure_ascii=False, default=str))
    else:
        console.print(data)


def _api_exit(exc: Exception) -> None:
    logger.error("api_fail err=%s", exc)
    console.print(f"[red]API failed[/] {exc}")
    sys.exit(EXIT_API)


@click.group()
@click.version_option(__version__, prog_name="newsc")
@click.option("--verbose", is_flag=True, help="DEBUG logs on stderr")
@click.option("--api-url", envvar="NEWSC_API_URL", default=None, help="Orchestrator base URL")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["json", "text"]),
    default="json",
    help="Output format (data on stdout)",
)
@click.pass_context
def main(ctx: click.Context, verbose: bool, api_url: str | None, fmt: str) -> None:
    """NewsC unified CLI — pipelines, AI jobs, vault, sources (HTTP only)."""
    _setup_logging(verbose)
    ctx.ensure_object(dict)
    ctx.obj["client"] = NewsCClient(api_url)
    ctx.obj["fmt"] = fmt


@main.command("health")
@click.pass_context
def health_cmd(ctx: click.Context) -> None:
    """GET /health."""
    try:
        data = ctx.obj["client"].health()
    except httpx.HTTPError as exc:
        _api_exit(exc)
    _emit(data, ctx.obj["fmt"])
    if not data.get("ok"):
        sys.exit(EXIT_API)
    sys.exit(EXIT_OK)


@main.group("pipeline")
def pipeline_group() -> None:
    """Run ingest pipelines."""


@pipeline_group.command("run")
@click.argument("pipeline_id", type=click.Choice(PIPELINE_IDS, case_sensitive=False))
@click.pass_context
def pipeline_run_cmd(ctx: click.Context, pipeline_id: str) -> None:
    """POST /pipelines/{id}/run (demo ids or sources)."""
    logger.info("pipeline_run id=%s", pipeline_id)
    try:
        data = ctx.obj["client"].pipeline_run(pipeline_id)
    except httpx.HTTPError as exc:
        _api_exit(exc)
    _emit(data, ctx.obj["fmt"])
    if pipeline_id == "sources" and data.get("total", 0) == 0 and data.get("inserted", 0) == 0:
        if data.get("sources_run", 0) == 0:
            sys.exit(EXIT_EMPTY)
    sys.exit(EXIT_OK)


@main.group("ai")
def ai_group() -> None:
    """AI job processing."""


@ai_group.command("process")
@click.option("--limit", default=20, show_default=True, type=int)
@click.option("--digest/--no-digest", default=True, show_default=True)
@click.pass_context
def ai_process_cmd(ctx: click.Context, limit: int, digest: bool) -> None:
    """POST /ai/jobs/process."""
    logger.info("ai_process limit=%s digest=%s", limit, digest)
    try:
        data = ctx.obj["client"].ai_process(limit=limit, include_digest=digest)
    except httpx.HTTPError as exc:
        _api_exit(exc)
    _emit(data, ctx.obj["fmt"])
    sys.exit(EXIT_OK)


@main.group("vault")
def vault_group() -> None:
    """Digest HTML vault (directory sources)."""


@vault_group.command("status")
@click.pass_context
def vault_status_cmd(ctx: click.Context) -> None:
    """GET /digests/vault/status."""
    try:
        data = ctx.obj["client"].vault_status()
    except httpx.HTTPError as exc:
        _api_exit(exc)
    _emit(data, ctx.obj["fmt"])
    sys.exit(EXIT_OK)


@vault_group.command("files")
@click.option("--source", default=None, help="Vault source id")
@click.option("--limit", default=50, type=int)
@click.option("-q", "query", default=None, help="Filename keyword")
@click.pass_context
def vault_files_cmd(ctx: click.Context, source: str | None, limit: int, query: str | None) -> None:
    """GET /digests/vault/files."""
    try:
        data = ctx.obj["client"].vault_files(source=source, limit=limit, q=query)
    except httpx.HTTPError as exc:
        _api_exit(exc)
    _emit(data, ctx.obj["fmt"])
    if data.get("count", 0) == 0:
        sys.exit(EXIT_EMPTY)
    sys.exit(EXIT_OK)


@vault_group.command("file")
@click.option("--source", required=True)
@click.option("--path", "rel_path", required=True)
@click.pass_context
def vault_file_cmd(ctx: click.Context, source: str, rel_path: str) -> None:
    """GET /digests/vault/file."""
    try:
        data = ctx.obj["client"].vault_file(source=source, path=rel_path)
    except httpx.HTTPError as exc:
        _api_exit(exc)
    _emit(data, ctx.obj["fmt"])
    sys.exit(EXIT_OK)


@main.group("digest")
def digest_group() -> None:
    """Digest read helpers."""


@digest_group.command("today")
@click.pass_context
def digest_today_cmd(ctx: click.Context) -> None:
    """GET /digests/today."""
    try:
        data = ctx.obj["client"].digest_today()
    except httpx.HTTPError as exc:
        _api_exit(exc)
    _emit(data, ctx.obj["fmt"])
    if data.get("empty"):
        sys.exit(EXIT_EMPTY)
    sys.exit(EXIT_OK)


@main.command("items")
@click.option("--limit", default=20, type=int, show_default=True)
@click.pass_context
def items_cmd(ctx: click.Context, limit: int) -> None:
    """GET /items."""
    try:
        data = ctx.obj["client"].items(limit=limit)
    except httpx.HTTPError as exc:
        _api_exit(exc)
    _emit(data, ctx.obj["fmt"])
    if data.get("count", 0) == 0:
        sys.exit(EXIT_EMPTY)
    sys.exit(EXIT_OK)


@main.group("sources")
def sources_group() -> None:
    """Subscription sources (DB)."""


@sources_group.command("list")
@click.pass_context
def sources_list_cmd(ctx: click.Context) -> None:
    """GET /sources."""
    try:
        data = ctx.obj["client"].sources_list()
    except httpx.HTTPError as exc:
        _api_exit(exc)
    _emit(data, ctx.obj["fmt"])
    if not data.get("sources"):
        sys.exit(EXIT_EMPTY)
    sys.exit(EXIT_OK)


@sources_group.command("add")
@click.option("--name", required=True)
@click.option("--type", "stype", type=click.Choice(SOURCE_TYPES), required=True)
@click.option("--url", default=None, help="For web/rss")
@click.option("--account", default=None, help="For youtube/bilibili")
@click.option("--handle", default=None, help="For social")
@click.option("--platform", default="other", help="Social platform")
@click.option("--disabled", is_flag=True, help="Create as disabled")
@click.pass_context
def sources_add_cmd(
    ctx: click.Context,
    name: str,
    stype: str,
    url: str | None,
    account: str | None,
    handle: str | None,
    platform: str,
    disabled: bool,
) -> None:
    """POST /sources."""
    config: dict[str, Any] = {}
    if stype in ("web", "rss"):
        if not url:
            console.print("[red]--url required for web/rss[/]")
            sys.exit(EXIT_VALID)
        config["url"] = url
    elif stype in ("youtube", "bilibili"):
        if not account:
            console.print("[red]--account required for youtube/bilibili[/]")
            sys.exit(EXIT_VALID)
        config["account"] = account
    elif stype == "social":
        if not handle:
            console.print("[red]--handle required for social[/]")
            sys.exit(EXIT_VALID)
        config["handle"] = handle
        config["platform"] = platform
    try:
        data = ctx.obj["client"].source_create(
            name=name, type_=stype, config=config, enabled=not disabled
        )
    except httpx.HTTPError as exc:
        _api_exit(exc)
    _emit(data, ctx.obj["fmt"])
    sys.exit(EXIT_OK)


@sources_group.command("update")
@click.argument("source_id")
@click.option("--name", default=None)
@click.option("--url", default=None)
@click.option("--account", default=None)
@click.option("--handle", default=None)
@click.option("--platform", default=None)
@click.pass_context
def sources_update_cmd(
    ctx: click.Context,
    source_id: str,
    name: str | None,
    url: str | None,
    account: str | None,
    handle: str | None,
    platform: str | None,
) -> None:
    """PATCH /sources/{id} (name/config)."""
    config: dict[str, Any] | None = None
    if url is not None:
        config = {"url": url}
    elif account is not None:
        config = {"account": account}
    elif handle is not None:
        config = {"handle": handle}
        if platform:
            config["platform"] = platform
    if name is None and config is None:
        console.print("[red]provide --name and/or config flags[/]")
        sys.exit(EXIT_VALID)
    try:
        data = ctx.obj["client"].source_update(source_id, name=name, config=config)
    except httpx.HTTPError as exc:
        _api_exit(exc)
    _emit(data, ctx.obj["fmt"])
    sys.exit(EXIT_OK)


@sources_group.command("enable")
@click.argument("source_id")
@click.pass_context
def sources_enable_cmd(ctx: click.Context, source_id: str) -> None:
    try:
        data = ctx.obj["client"].source_update(source_id, enabled=True)
    except httpx.HTTPError as exc:
        _api_exit(exc)
    _emit(data, ctx.obj["fmt"])
    sys.exit(EXIT_OK)


@sources_group.command("disable")
@click.argument("source_id")
@click.pass_context
def sources_disable_cmd(ctx: click.Context, source_id: str) -> None:
    try:
        data = ctx.obj["client"].source_update(source_id, enabled=False)
    except httpx.HTTPError as exc:
        _api_exit(exc)
    _emit(data, ctx.obj["fmt"])
    sys.exit(EXIT_OK)


@sources_group.command("delete")
@click.argument("source_id")
@click.pass_context
def sources_delete_cmd(ctx: click.Context, source_id: str) -> None:
    try:
        data = ctx.obj["client"].source_delete(source_id)
    except httpx.HTTPError as exc:
        _api_exit(exc)
    _emit(data, ctx.obj["fmt"])
    sys.exit(EXIT_OK)


@main.group("vault-source")
def vault_source_group() -> None:
    """Manage digest-sources.yml entries via API."""


@vault_source_group.command("add")
@click.option("--id", "source_id", required=True)
@click.option("--label", required=True)
@click.option("--path", "src_path", required=True)
@click.option("--disabled", is_flag=True)
@click.pass_context
def vault_source_add_cmd(
    ctx: click.Context,
    source_id: str,
    label: str,
    src_path: str,
    disabled: bool,
) -> None:
    try:
        data = ctx.obj["client"].vault_source_upsert(
            source_id=source_id,
            label=label,
            path=src_path,
            enabled=not disabled,
        )
    except httpx.HTTPError as exc:
        _api_exit(exc)
    _emit(data, ctx.obj["fmt"])
    sys.exit(EXIT_OK)


@vault_source_group.command("enable")
@click.argument("source_id")
@click.pass_context
def vault_source_enable_cmd(ctx: click.Context, source_id: str) -> None:
    try:
        data = ctx.obj["client"].vault_source_set_enabled(source_id, True)
    except httpx.HTTPError as exc:
        _api_exit(exc)
    _emit(data, ctx.obj["fmt"])
    sys.exit(EXIT_OK)


@vault_source_group.command("disable")
@click.argument("source_id")
@click.pass_context
def vault_source_disable_cmd(ctx: click.Context, source_id: str) -> None:
    try:
        data = ctx.obj["client"].vault_source_set_enabled(source_id, False)
    except httpx.HTTPError as exc:
        _api_exit(exc)
    _emit(data, ctx.obj["fmt"])
    sys.exit(EXIT_OK)


@vault_source_group.command("delete")
@click.argument("source_id")
@click.pass_context
def vault_source_delete_cmd(ctx: click.Context, source_id: str) -> None:
    try:
        data = ctx.obj["client"].vault_source_delete(source_id)
    except httpx.HTTPError as exc:
        _api_exit(exc)
    _emit(data, ctx.obj["fmt"])
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
