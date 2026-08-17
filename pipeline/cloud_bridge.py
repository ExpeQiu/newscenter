"""Mac ↔ 云 控制面桥接：合并 marks、消费 outbox、对账 sources、执行指令。

用法:
  python -m pipeline.cloud_bridge           # marks + outbox + sources
  python -m pipeline.cloud_bridge --marks-only
  python -m pipeline.cloud_bridge --drain-only
  python -m pipeline.cloud_bridge --sources-only
"""
from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.db import SessionLocal, init_db  # noqa: E402
from pipeline.models import CloudOutbox, Item, Mark, Source  # noqa: E402

logger = logging.getLogger("newsc.cloud_bridge")

# 仓库内配置；launchd 在 iCloud 路径下可能无法读取，故同时支持 Application Support 副本
CLOUD_ENV = ROOT / ".env.cloud.local"
CLOUD_ENV_APP_SUPPORT = Path.home() / "Library" / "Application Support" / "newsc" / ".env.cloud.local"


def _cloud_env_path() -> Path:
    if CLOUD_ENV_APP_SUPPORT.is_file():
        return CLOUD_ENV_APP_SUPPORT
    return CLOUD_ENV


def _load_dotenv_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip("'").strip('"')
    return out


def _normalize_sa_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def _cloud_session() -> Session:
    env = _load_dotenv_file(_cloud_env_path())
    raw = os.environ.get("CLOUD_DATABASE_URL") or env.get("CLOUD_DATABASE_URL") or ""
    if not raw.strip():
        raise RuntimeError("缺少 CLOUD_DATABASE_URL（.env.cloud.local 或 Application Support 副本）")
    engine = create_engine(
        _normalize_sa_url(raw),
        pool_pre_ping=True,
        connect_args={"connect_timeout": 8},
    )
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()


def _ensure_tunnel() -> None:
    script = ROOT / "scripts" / "deploy" / "db-tunnel.sh"
    if not script.is_file():
        return
    env = _load_dotenv_file(_cloud_env_path())
    port = int(env.get("NEWSC_TUNNEL_LOCAL_PORT") or os.environ.get("NEWSC_TUNNEL_LOCAL_PORT") or "15434")
    try:
        import socket

        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            return
    except OSError:
        pass
    logger.info("cloud_bridge_tunnel_start port=%s", port)
    try:
        subprocess.run(
            ["bash", str(script), "-d"],
            cwd=str(ROOT),
            check=False,
            timeout=45,
            capture_output=True,
            text=True,
        )
    except subprocess.TimeoutExpired:
        logger.warning("cloud_bridge_tunnel_timeout port=%s", port)


def merge_marks_from_cloud(*, local: Session, cloud: Session) -> dict[str, int]:
    """云端较新的 marks 写入本机（按 item_id + updated_at）。"""
    cloud_rows = cloud.query(Mark).all()
    applied = 0
    skipped = 0
    missing_item = 0
    for cm in cloud_rows:
        item = local.query(Item).filter(Item.id == cm.item_id).first()
        if not item:
            missing_item += 1
            continue
        lm = local.query(Mark).filter(Mark.item_id == cm.item_id).first()
        c_ts = cm.updated_at or datetime.min.replace(tzinfo=timezone.utc)
        if lm:
            l_ts = lm.updated_at or datetime.min.replace(tzinfo=timezone.utc)
            if c_ts <= l_ts:
                skipped += 1
                continue
            lm.is_read = cm.is_read
            lm.is_starred = cm.is_starred
            lm.is_archived = cm.is_archived
            lm.note = cm.note
            lm.updated_at = c_ts
        else:
            local.add(
                Mark(
                    id=cm.id,
                    item_id=cm.item_id,
                    is_read=cm.is_read,
                    is_starred=cm.is_starred,
                    is_archived=cm.is_archived,
                    note=cm.note,
                    updated_at=c_ts,
                )
            )
        applied += 1
    local.commit()
    logger.info(
        "marks_merge applied=%s skipped=%s missing_item=%s cloud_total=%s",
        applied,
        skipped,
        missing_item,
        len(cloud_rows),
    )
    return {
        "applied": applied,
        "skipped": skipped,
        "missing_item": missing_item,
        "cloud_total": len(cloud_rows),
    }


def _write_cloud_env(values: dict[str, str]) -> None:
    lines = [
        "# 由 cloud_bridge / 设置页写入 · 勿提交",
        f"DEPLOY_HOST={values.get('DEPLOY_HOST', '')}",
        f"DEPLOY_DIR={values.get('DEPLOY_DIR', '')}",
        f"CLOUD_DATABASE_URL={values.get('CLOUD_DATABASE_URL', '')}",
        f"NEWSC_TUNNEL_LOCAL_PORT={values.get('NEWSC_TUNNEL_LOCAL_PORT', '15434')}",
        f"LOCAL_DATABASE_URL={values.get('LOCAL_DATABASE_URL', '')}",
        f"PUSH_SCHEDULE_ENABLED={values.get('PUSH_SCHEDULE_ENABLED', '0')}",
        f"PUSH_SCHEDULE_MODE={values.get('PUSH_SCHEDULE_MODE', 'daily')}",
        f"PUSH_SCHEDULE_TIMES={values.get('PUSH_SCHEDULE_TIMES', '09:00,12:00,16:00,20:00')}",
        f"PUSH_SCHEDULE_INTERVAL_HOURS={values.get('PUSH_SCHEDULE_INTERVAL_HOURS', '6')}",
        "",
    ]
    text = "\n".join(lines)
    for path in (CLOUD_ENV, CLOUD_ENV_APP_SUPPORT):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            os.chmod(path, 0o600)
        except OSError as exc:
            logger.warning("cloud_env_write_fail path=%s err=%s", path, exc)
    logger.info("cloud_env_written paths=%s", [str(CLOUD_ENV), str(CLOUD_ENV_APP_SUPPORT)])


def _apply_source_upsert(local: Session, payload: dict[str, Any]) -> dict[str, Any]:
    sid = str(payload.get("id") or "")
    if not sid:
        raise ValueError("source id required")
    row = local.query(Source).filter(Source.id == sid).first()
    name = str(payload.get("name") or "").strip() or "unnamed"
    stype = str(payload.get("type") or "rss").strip().lower()
    config = dict(payload.get("config") or {})
    enabled = bool(payload.get("enabled", True))
    if row:
        row.name = name
        row.type = stype
        row.config = config
        row.enabled = enabled
        action = "updated"
    else:
        local.add(Source(id=sid, name=name, type=stype, config=config, enabled=enabled))
        action = "created"
    local.commit()
    logger.info("outbox_source_upsert id=%s action=%s", sid, action)
    return {"id": sid, "action": action}


def reconcile_sources_from_cloud(*, local: Session, cloud: Session) -> dict[str, int]:
    """云端 sources 按 id 下行 upsert 到本机。

    采集真源在 Mac：若只依赖 outbox 且 Agent 曾中断，云端新增的 YouTube 等源会丢，
    随后 push-db 还会用本机缺源快照盖掉云端。每次 bridge 对账一次以自愈。
    不覆盖本机 cursor（增量游标以本机采集为准）。
    """
    cloud_rows = cloud.query(Source).all()
    created = 0
    updated = 0
    unchanged = 0
    for cs in cloud_rows:
        row = local.query(Source).filter(Source.id == cs.id).first()
        cfg = dict(cs.config or {})
        if row is None:
            local.add(
                Source(
                    id=cs.id,
                    name=cs.name,
                    type=cs.type,
                    config=cfg,
                    enabled=bool(cs.enabled),
                    cursor=dict(cs.cursor) if isinstance(cs.cursor, dict) else cs.cursor,
                )
            )
            created += 1
            continue
        same = (
            row.name == cs.name
            and row.type == cs.type
            and (row.config or {}) == cfg
            and bool(row.enabled) == bool(cs.enabled)
        )
        if same:
            unchanged += 1
            continue
        row.name = cs.name
        row.type = cs.type
        row.config = cfg
        row.enabled = bool(cs.enabled)
        updated += 1
    local.commit()
    logger.info(
        "sources_reconcile created=%s updated=%s unchanged=%s cloud_total=%s",
        created,
        updated,
        unchanged,
        len(cloud_rows),
    )
    return {
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "cloud_total": len(cloud_rows),
    }


def requeue_stale_outbox_claims(
    cloud: Session, *, older_than_sec: int = 900
) -> dict[str, int]:
    """将长时间卡在 claimed 的 outbox 重新置为 pending，避免 Agent 崩溃后指令丢失。"""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=older_than_sec)
    rows = (
        cloud.query(CloudOutbox)
        .filter(CloudOutbox.status == "claimed", CloudOutbox.claimed_at.isnot(None))
        .all()
    )
    n = 0
    for row in rows:
        claimed = row.claimed_at
        if claimed is not None and claimed.tzinfo is None:
            claimed = claimed.replace(tzinfo=timezone.utc)
        if claimed is None or claimed > cutoff:
            continue
        row.status = "pending"
        row.claimed_at = None
        prev = (row.error or "").strip()
        note = "requeued_stale_claim"
        row.error = f"{prev} | {note}" if prev else note
        n += 1
    if n:
        cloud.commit()
    logger.info("outbox_requeue_stale claimed_reset=%s older_than_sec=%s", n, older_than_sec)
    return {"requeued": n}


def _apply_source_delete(local: Session, payload: dict[str, Any]) -> dict[str, Any]:
    sid = str(payload.get("id") or "")
    row = local.query(Source).filter(Source.id == sid).first()
    if not row:
        return {"id": sid, "deleted": False, "reason": "not_found"}
    from pipeline.ingest import purge_source_items

    purged = purge_source_items(local, sid)
    local.delete(row)
    local.commit()
    logger.info("outbox_source_delete id=%s purged=%s", sid, purged)
    return {"id": sid, "deleted": True, "purged_items": purged}


def _apply_vault_source(payload: dict[str, Any], *, delete: bool = False) -> dict[str, Any]:
    from pipeline.digest_vault import (
        delete_source as vault_delete_source,
        set_source_enabled as vault_set_enabled,
        upsert_source as vault_upsert_source,
    )

    sid = str(payload.get("id") or "").strip()
    if not sid:
        raise ValueError("vault source id required")
    if delete:
        return vault_delete_source(sid)
    if "enabled" in payload and not payload.get("path") and not payload.get("label"):
        return vault_set_enabled(sid, bool(payload.get("enabled", True)))
    path = str(payload.get("path") or "").strip()
    if not path:
        raise ValueError("vault source path required")
    return vault_upsert_source(
        source_id=sid,
        label=str(payload.get("label") or sid),
        path=path,
        enabled=bool(payload.get("enabled", True)),
        refresh_interval=payload.get("refresh_interval"),
        tags=payload.get("tags"),
    )


def _apply_sync_config(payload: dict[str, Any]) -> dict[str, Any]:
    existing = _load_dotenv_file(_cloud_env_path())
    cloud_url = str(payload.get("cloud_database_url") or "").strip()
    if not cloud_url or "***" in cloud_url:
        cloud_url = existing.get("CLOUD_DATABASE_URL", "")
    values = {
        "DEPLOY_HOST": str(payload.get("deploy_host") or existing.get("DEPLOY_HOST") or "120.25.145.131"),
        "DEPLOY_DIR": str(payload.get("deploy_dir") or existing.get("DEPLOY_DIR") or "/opt/newsc"),
        "NEWSC_TUNNEL_LOCAL_PORT": str(
            payload.get("tunnel_local_port") or existing.get("NEWSC_TUNNEL_LOCAL_PORT") or "15434"
        ),
        "CLOUD_DATABASE_URL": cloud_url,
        "LOCAL_DATABASE_URL": str(
            payload.get("local_database_url")
            or existing.get("LOCAL_DATABASE_URL")
            or "postgresql://qiubin@/newsc?host=/tmp"
        ),
        "PUSH_SCHEDULE_ENABLED": "1" if payload.get("push_schedule_enabled") else "0",
        "PUSH_SCHEDULE_MODE": str(payload.get("push_schedule_mode") or "daily"),
        "PUSH_SCHEDULE_TIMES": ",".join(payload.get("push_schedule_times") or [])
        or existing.get("PUSH_SCHEDULE_TIMES")
        or "09:00,12:00,16:00,20:00",
        "PUSH_SCHEDULE_INTERVAL_HOURS": str(payload.get("push_schedule_interval_hours") or 6),
    }
    if isinstance(payload.get("push_schedule_times"), str):
        values["PUSH_SCHEDULE_TIMES"] = payload["push_schedule_times"]
    _write_cloud_env(values)
    apply = bool(payload.get("apply_schedule", True))
    schedule_out = ""
    if apply:
        script = ROOT / "scripts" / "deploy" / "install-push-db-launchd.sh"
        action = "install" if values["PUSH_SCHEDULE_ENABLED"] == "1" else "uninstall"
        proc = subprocess.run(
            ["bash", str(script), action],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        schedule_out = ((proc.stdout or "") + (proc.stderr or "")).strip()[-1500:]
    logger.info("outbox_sync_config saved schedule_apply=%s", apply)
    return {"saved": True, "schedule": schedule_out}


def _run_script(rel: str, args: list[str] | None = None, *, timeout: int = 600) -> dict[str, Any]:
    script = ROOT / rel
    cmd = ["bash", str(script), *(args or [])]
    logger.info("outbox_run_script cmd=%s", " ".join(cmd))
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    out = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    return {"returncode": proc.returncode, "ok": proc.returncode == 0, "output": out[-4000:]}


def _apply_one(local: Session, row: CloudOutbox) -> dict[str, Any]:
    kind = row.kind
    payload = dict(row.payload or {})
    if kind == "source.upsert":
        return _apply_source_upsert(local, payload)
    if kind == "source.delete":
        return _apply_source_delete(local, payload)
    if kind == "vault_source.upsert":
        return _apply_vault_source(payload, delete=False)
    if kind == "vault_source.delete":
        return _apply_vault_source(payload, delete=True)
    if kind == "sync.save_config":
        return _apply_sync_config(payload)
    if kind == "sync.ensure_tunnel":
        return _run_script("scripts/deploy/db-tunnel.sh", ["-d"], timeout=60)
    if kind == "sync.push_db":
        args = ["--dry-run"] if payload.get("dry_run") else []
        return _run_script("scripts/deploy/push-db-to-cloud.sh", args, timeout=600)
    if kind == "pipeline.run":
        # 经本机 orchestrator HTTP 更稳；失败则记错
        import httpx

        pid = str(payload.get("pipeline_id") or "sources")
        base = os.environ.get("NEWSC_API_URL") or "http://127.0.0.1:8787"
        params: dict[str, Any] = {}
        if pid == "insight":
            params["force"] = "true" if payload.get("force") else "false"
            params["kind"] = str(payload.get("kind") or "all")
        r = httpx.post(
            f"{base.rstrip('/')}/pipelines/{pid}/run",
            params=params or None,
            timeout=180,
        )
        r.raise_for_status()
        return r.json()
    raise ValueError(f"unknown outbox kind: {kind}")


def drain_outbox(*, local: Session, cloud: Session, limit: int = 50) -> dict[str, Any]:
    """领取并执行云端 pending 指令。"""
    from pipeline.models import Base

    Base.metadata.create_all(bind=cloud.get_bind())
    requeue_stale_outbox_claims(cloud)

    skip_raw = (os.environ.get("CLOUD_BRIDGE_SKIP_KINDS") or "").strip()
    skip = {k.strip() for k in skip_raw.split(",") if k.strip()}

    q = (
        cloud.query(CloudOutbox)
        .filter(CloudOutbox.status == "pending")
        .order_by(CloudOutbox.created_at.asc())
    )
    rows = q.limit(limit * 2).all()
    rows = [r for r in rows if r.kind not in skip][:limit]
    done = 0
    failed = 0
    results: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    for row in rows:
        row.status = "claimed"
        row.claimed_at = now
        cloud.commit()
        try:
            result = _apply_one(local, row)
            row.status = "done"
            row.done_at = datetime.now(timezone.utc)
            row.result = result if isinstance(result, dict) else {"result": result}
            row.error = None
            done += 1
            results.append({"id": row.id, "kind": row.kind, "ok": True})
            logger.info("outbox_done id=%s kind=%s", row.id, row.kind)
        except Exception as exc:  # noqa: BLE001
            row.status = "failed"
            row.done_at = datetime.now(timezone.utc)
            row.error = str(exc)[:2000]
            failed += 1
            results.append({"id": row.id, "kind": row.kind, "ok": False, "error": str(exc)[:300]})
            logger.exception("outbox_fail id=%s kind=%s", row.id, row.kind)
        cloud.commit()
    return {"claimed": len(rows), "done": done, "failed": failed, "results": results}


def run_once(
    *,
    marks: bool = True,
    drain: bool = True,
    sources: bool = True,
) -> dict[str, Any]:
    init_db()
    _ensure_tunnel()
    local = SessionLocal()
    cloud = _cloud_session()
    out: dict[str, Any] = {}
    try:
        # 本机也建表，便于日后对称
        from pipeline.models import Base

        Base.metadata.create_all(bind=local.get_bind())
        if marks:
            out["marks"] = merge_marks_from_cloud(local=local, cloud=cloud)
        if drain:
            out["outbox"] = drain_outbox(local=local, cloud=cloud)
        # 源对账放在 outbox 之后：删除指令先落地，再补齐仍存在于云端的源
        if sources:
            out["sources"] = reconcile_sources_from_cloud(local=local, cloud=cloud)
        logger.info("cloud_bridge_ok keys=%s", list(out.keys()))
        return out
    finally:
        local.close()
        cloud.close()


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    p = argparse.ArgumentParser(description="Mac ← 云 控制面桥接")
    p.add_argument("--marks-only", action="store_true")
    p.add_argument("--drain-only", action="store_true")
    p.add_argument("--sources-only", action="store_true", help="仅对账云端 sources → 本机")
    args = p.parse_args(argv)
    marks = True
    drain = True
    sources = True
    if args.sources_only:
        marks = drain = False
        sources = True
    elif args.marks_only:
        marks = True
        drain = False
        # 推库前 marks-only 也必须对账源，避免缺源 dump 盖掉云端订阅
        sources = True
    elif args.drain_only:
        marks = False
        drain = True
        sources = True
    try:
        result = run_once(marks=marks, drain=drain, sources=sources)
        print(result)
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.exception("cloud_bridge_fatal")
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
