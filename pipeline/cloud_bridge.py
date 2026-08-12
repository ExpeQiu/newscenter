"""Mac ↔ 云 控制面桥接：合并 marks、消费 outbox、执行指令。

用法:
  python -m pipeline.cloud_bridge           # 拉 marks + drain outbox
  python -m pipeline.cloud_bridge --marks-only
  python -m pipeline.cloud_bridge --drain-only
"""
from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
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

CLOUD_ENV = ROOT / ".env.cloud.local"


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
    env = _load_dotenv_file(CLOUD_ENV)
    raw = os.environ.get("CLOUD_DATABASE_URL") or env.get("CLOUD_DATABASE_URL") or ""
    if not raw.strip():
        raise RuntimeError("缺少 CLOUD_DATABASE_URL（.env.cloud.local）")
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
    env = _load_dotenv_file(CLOUD_ENV)
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
    CLOUD_ENV.write_text("\n".join(lines), encoding="utf-8")
    try:
        os.chmod(CLOUD_ENV, 0o600)
    except OSError:
        pass


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
    )


def _apply_sync_config(payload: dict[str, Any]) -> dict[str, Any]:
    existing = _load_dotenv_file(CLOUD_ENV)
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
        r = httpx.post(f"{base.rstrip('/')}/pipelines/{pid}/run", timeout=120)
        r.raise_for_status()
        return r.json()
    raise ValueError(f"unknown outbox kind: {kind}")


def drain_outbox(*, local: Session, cloud: Session, limit: int = 50) -> dict[str, Any]:
    """领取并执行云端 pending 指令。"""
    from pipeline.models import Base

    Base.metadata.create_all(bind=cloud.get_bind())

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


def run_once(*, marks: bool = True, drain: bool = True) -> dict[str, Any]:
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
    args = p.parse_args(argv)
    marks = not args.drain_only
    drain = not args.marks_only
    if args.marks_only:
        drain = False
    if args.drain_only:
        marks = False
    try:
        result = run_once(marks=marks, drain=drain)
        print(result)
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.exception("cloud_bridge_fatal")
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
