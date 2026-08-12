"""本机 → 云端数据库同步配置（读写 .env.cloud.local，触发 push-db / 定时）。"""
from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote, unquote, urlparse, urlunparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from pipeline.db import get_db
from pipeline.outbox import enqueue, get_control_setting, upsert_control_setting
from pipeline.runtime import is_cloud_runtime

logger = logging.getLogger("newsc.orchestrator.cloud_sync")
router = APIRouter(tags=["cloud-sync"])

ROOT = Path(__file__).resolve().parents[2]
CLOUD_ENV = ROOT / ".env.cloud.local"
PUSH_SCRIPT = ROOT / "scripts" / "deploy" / "push-db-to-cloud.sh"
TUNNEL_SCRIPT = ROOT / "scripts" / "deploy" / "db-tunnel.sh"
SCHEDULE_SCRIPT = ROOT / "scripts" / "deploy" / "install-push-db-launchd.sh"
PUSH_LOG = ROOT / "logs" / "push-db-to-cloud.log"
LAUNCHD_LABEL = "com.newsc.push-db-cloud"

MASK = "***"
DEFAULT_TIMES = "08:25,12:15,18:25,21:15"
DEFAULTS = {
    "DEPLOY_HOST": "120.25.145.131",
    "DEPLOY_DIR": "/opt/newsc",
    "NEWSC_TUNNEL_LOCAL_PORT": "15434",
    "CLOUD_DATABASE_URL": "",
    "LOCAL_DATABASE_URL": "postgresql://qiubin@/newsc?host=/tmp",
    "PUSH_SCHEDULE_ENABLED": "0",
    "PUSH_SCHEDULE_MODE": "daily",
    "PUSH_SCHEDULE_TIMES": DEFAULT_TIMES,
    "PUSH_SCHEDULE_INTERVAL_HOURS": "6",
}

TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


class CloudSyncConfigIn(BaseModel):
    deploy_host: str = Field(default="", max_length=253)
    deploy_dir: str = Field(default="", max_length=512)
    tunnel_local_port: int = Field(default=15434, ge=1024, le=65535)
    cloud_database_url: str = Field(default="", max_length=2048)
    local_database_url: str = Field(default="", max_length=2048)
    push_schedule_enabled: bool = False
    push_schedule_mode: Literal["daily", "interval"] = "daily"
    push_schedule_times: list[str] = Field(default_factory=lambda: DEFAULT_TIMES.split(","))
    push_schedule_interval_hours: int = Field(default=6, ge=1, le=168)
    apply_schedule: bool = True

    @field_validator("push_schedule_times")
    @classmethod
    def _times_ok(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for raw in v:
            t = (raw or "").strip()
            if not t:
                continue
            if not TIME_RE.match(t):
                raise ValueError(f"时刻格式无效: {t}（需 HH:MM）")
            hh, mm = t.split(":")
            out.append(f"{int(hh):02d}:{int(mm):02d}")
        return out


class CloudSyncPushIn(BaseModel):
    dry_run: bool = False


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("'").strip('"')
        if key:
            out[key] = val
    return out


def _env_truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "on"}


def _parse_times(raw: str) -> list[str]:
    out: list[str] = []
    for part in (raw or "").split(","):
        t = part.strip()
        if not t:
            continue
        m = TIME_RE.match(t)
        if not m:
            continue
        out.append(f"{int(m.group(1)):02d}:{int(m.group(2)):02d}")
    return out or DEFAULT_TIMES.split(",")


def _mask_pg_url(url: str) -> str:
    if not url or "://" not in url:
        return url
    try:
        p = urlparse(url)
        if not p.password:
            return url
        user = unquote(p.username or "")
        host = p.hostname or ""
        port = f":{p.port}" if p.port else ""
        netloc = f"{quote(user, safe='')}:{MASK}@{host}{port}"
        return urlunparse((p.scheme, netloc, p.path, p.params, p.query, p.fragment))
    except Exception:
        return re.sub(r"(://[^:/@]+:)([^@]+)(@)", rf"\1{MASK}\3", url)


def _is_masked_url(url: str) -> bool:
    return f":{MASK}@" in (url or "")


def _write_env(values: dict[str, str]) -> None:
    lines = [
        "# 由设置页 / orchestrator 写入 · 勿提交",
        f"DEPLOY_HOST={values.get('DEPLOY_HOST', '')}",
        f"DEPLOY_DIR={values.get('DEPLOY_DIR', '')}",
        f"CLOUD_DATABASE_URL={values.get('CLOUD_DATABASE_URL', '')}",
        f"NEWSC_TUNNEL_LOCAL_PORT={values.get('NEWSC_TUNNEL_LOCAL_PORT', '15434')}",
        f"LOCAL_DATABASE_URL={values.get('LOCAL_DATABASE_URL', '')}",
        f"PUSH_SCHEDULE_ENABLED={values.get('PUSH_SCHEDULE_ENABLED', '0')}",
        f"PUSH_SCHEDULE_MODE={values.get('PUSH_SCHEDULE_MODE', 'daily')}",
        f"PUSH_SCHEDULE_TIMES={values.get('PUSH_SCHEDULE_TIMES', DEFAULT_TIMES)}",
        f"PUSH_SCHEDULE_INTERVAL_HOURS={values.get('PUSH_SCHEDULE_INTERVAL_HOURS', '6')}",
        "",
    ]
    CLOUD_ENV.write_text("\n".join(lines), encoding="utf-8")
    try:
        os.chmod(CLOUD_ENV, 0o600)
    except OSError:
        pass


def _schedule_installed() -> bool:
    try:
        proc = subprocess.run(
            ["launchctl", "print", f"gui/{os.getuid()}/{LAUNCHD_LABEL}"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _apply_launchd(*, enabled: bool) -> dict[str, Any]:
    if not SCHEDULE_SCRIPT.is_file():
        raise HTTPException(500, f"缺少脚本: {SCHEDULE_SCRIPT}")
    action = "install" if enabled else "uninstall"
    logger.info("cloud_sync_schedule_apply action=%s", action)
    try:
        proc = subprocess.run(
            ["bash", str(SCHEDULE_SCRIPT), action],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        logger.error("cloud_sync_schedule_timeout action=%s", action)
        raise HTTPException(504, "应用定时推送超时") from exc
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    ok = proc.returncode == 0
    installed = _schedule_installed()
    logger.info(
        "cloud_sync_schedule_done action=%s ok=%s rc=%s installed=%s",
        action,
        ok,
        proc.returncode,
        installed,
    )
    if not ok and enabled:
        raise HTTPException(500, f"应用定时推送失败：{out[-1500:] or f'rc={proc.returncode}'}")
    return {"ok": ok, "returncode": proc.returncode, "output": out[-2000:], "installed": installed}


def _config_payload(raw: dict[str, str], *, configured: bool) -> dict[str, Any]:
    cloud_url = raw.get("CLOUD_DATABASE_URL", "")
    port_raw = raw.get("NEWSC_TUNNEL_LOCAL_PORT") or DEFAULTS["NEWSC_TUNNEL_LOCAL_PORT"]
    try:
        port = int(port_raw)
    except ValueError:
        port = 15434
    try:
        interval_h = int(raw.get("PUSH_SCHEDULE_INTERVAL_HOURS") or "6")
    except ValueError:
        interval_h = 6
    mode = (raw.get("PUSH_SCHEDULE_MODE") or "daily").strip().lower()
    if mode not in {"daily", "interval"}:
        mode = "daily"
    times = _parse_times(raw.get("PUSH_SCHEDULE_TIMES") or DEFAULT_TIMES)
    enabled = _env_truthy(raw.get("PUSH_SCHEDULE_ENABLED"))
    return {
        "configured": configured,
        "config_path": str(CLOUD_ENV),
        "deploy_host": raw.get("DEPLOY_HOST") or DEFAULTS["DEPLOY_HOST"],
        "deploy_dir": raw.get("DEPLOY_DIR") or DEFAULTS["DEPLOY_DIR"],
        "tunnel_local_port": port,
        "cloud_database_url": _mask_pg_url(cloud_url) if cloud_url else "",
        "cloud_database_url_set": bool(cloud_url.strip()),
        "local_database_url": raw.get("LOCAL_DATABASE_URL")
        or DEFAULTS["LOCAL_DATABASE_URL"],
        "push_schedule_enabled": enabled,
        "push_schedule_mode": mode,
        "push_schedule_times": times,
        "push_schedule_interval_hours": max(1, min(168, interval_h)),
        "push_schedule_installed": _schedule_installed(),
    }


def _last_push_info() -> dict[str, Any]:
    if not PUSH_LOG.is_file():
        return {"log_path": str(PUSH_LOG), "exists": False, "tail": []}
    try:
        lines = PUSH_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        logger.warning("cloud_sync_log_read_fail err=%s", exc)
        return {"log_path": str(PUSH_LOG), "exists": True, "tail": [], "error": str(exc)}
    return {
        "log_path": str(PUSH_LOG),
        "exists": True,
        "mtime": PUSH_LOG.stat().st_mtime,
        "tail": lines[-40:],
    }


def _tunnel_listening(port: int) -> bool | None:
    """Best-effort：本机隧道端口是否在听。"""
    try:
        import socket

        with socket.create_connection(("127.0.0.1", port), timeout=0.4):
            return True
    except OSError:
        return False


@router.get("/cloud-sync/config")
def get_cloud_sync_config(db: Session = Depends(get_db)) -> dict[str, Any]:
    if is_cloud_runtime():
        snap = get_control_setting(db, "cloud_sync") or {}
        raw = {
            "DEPLOY_HOST": str(snap.get("deploy_host") or DEFAULTS["DEPLOY_HOST"]),
            "DEPLOY_DIR": str(snap.get("deploy_dir") or DEFAULTS["DEPLOY_DIR"]),
            "NEWSC_TUNNEL_LOCAL_PORT": str(
                snap.get("tunnel_local_port") or DEFAULTS["NEWSC_TUNNEL_LOCAL_PORT"]
            ),
            "CLOUD_DATABASE_URL": str(snap.get("cloud_database_url") or ""),
            "LOCAL_DATABASE_URL": str(
                snap.get("local_database_url") or DEFAULTS["LOCAL_DATABASE_URL"]
            ),
            "PUSH_SCHEDULE_ENABLED": "1" if snap.get("push_schedule_enabled") else "0",
            "PUSH_SCHEDULE_MODE": str(snap.get("push_schedule_mode") or "daily"),
            "PUSH_SCHEDULE_TIMES": ",".join(snap.get("push_schedule_times") or [])
            or DEFAULT_TIMES,
            "PUSH_SCHEDULE_INTERVAL_HOURS": str(snap.get("push_schedule_interval_hours") or 6),
        }
        configured = bool(snap)
        payload = _config_payload(raw, configured=configured)
        payload["runtime"] = "cloud"
        payload["tunnel_up"] = None
        payload["push_schedule_installed"] = bool(snap.get("push_schedule_enabled"))
        payload["control_note"] = "云端写入将进入 outbox，由 Mac Agent 执行"
        payload["last_push"] = _last_push_info()
        from pipeline.models import CloudOutbox

        pending = db.query(CloudOutbox).filter(CloudOutbox.status == "pending").count()
        payload["outbox_pending"] = pending
        return payload

    raw = _parse_env_file(CLOUD_ENV)
    configured = CLOUD_ENV.is_file() and bool(raw.get("CLOUD_DATABASE_URL", "").strip())
    payload = _config_payload(raw if raw else dict(DEFAULTS), configured=configured)
    port = int(payload["tunnel_local_port"])
    payload["tunnel_up"] = _tunnel_listening(port)
    payload["last_push"] = _last_push_info()
    payload["runtime"] = "local"
    payload["outbox_pending"] = 0
    logger.info(
        "cloud_sync_config_get configured=%s tunnel_up=%s schedule=%s/%s installed=%s",
        configured,
        payload["tunnel_up"],
        payload["push_schedule_enabled"],
        payload["push_schedule_mode"],
        payload["push_schedule_installed"],
    )
    return payload


@router.put("/cloud-sync/config")
def put_cloud_sync_config(
    body: CloudSyncConfigIn, db: Session = Depends(get_db)
) -> dict[str, Any]:
    if body.push_schedule_enabled and body.push_schedule_mode == "daily" and not body.push_schedule_times:
        raise HTTPException(400, "每日定点模式至少填写一个推送时刻（HH:MM）")

    times_csv = ",".join(body.push_schedule_times) if body.push_schedule_times else DEFAULT_TIMES
    snap = {
        "deploy_host": (body.deploy_host or "").strip() or DEFAULTS["DEPLOY_HOST"],
        "deploy_dir": (body.deploy_dir or "").strip() or DEFAULTS["DEPLOY_DIR"],
        "tunnel_local_port": body.tunnel_local_port or 15434,
        "cloud_database_url": (body.cloud_database_url or "").strip(),
        "local_database_url": (body.local_database_url or "").strip()
        or DEFAULTS["LOCAL_DATABASE_URL"],
        "push_schedule_enabled": body.push_schedule_enabled,
        "push_schedule_mode": body.push_schedule_mode,
        "push_schedule_times": body.push_schedule_times or DEFAULT_TIMES.split(","),
        "push_schedule_interval_hours": body.push_schedule_interval_hours,
        "apply_schedule": body.apply_schedule,
    }

    if is_cloud_runtime():
        # 云端不写本机文件；快照 + outbox 交给 Mac
        existing = get_control_setting(db, "cloud_sync") or {}
        if not snap["cloud_database_url"] or _is_masked_url(snap["cloud_database_url"]):
            snap["cloud_database_url"] = str(existing.get("cloud_database_url") or "")
        upsert_control_setting(db, "cloud_sync", snap)
        enqueue(db, "sync.save_config", snap)
        db.commit()
        logger.info("cloud_sync_config_enqueued host=%s schedule=%s", snap["deploy_host"], snap["push_schedule_enabled"])
        out = get_cloud_sync_config(db)
        out["enqueued"] = True
        return out

    existing = _parse_env_file(CLOUD_ENV)
    cloud_url = snap["cloud_database_url"]
    if not cloud_url or _is_masked_url(cloud_url):
        cloud_url = existing.get("CLOUD_DATABASE_URL", "").strip()
    if not cloud_url:
        raise HTTPException(400, "请填写 CLOUD_DATABASE_URL（经隧道访问云端 newsc 库）")

    values = {
        "DEPLOY_HOST": snap["deploy_host"],
        "DEPLOY_DIR": snap["deploy_dir"],
        "NEWSC_TUNNEL_LOCAL_PORT": str(snap["tunnel_local_port"]),
        "CLOUD_DATABASE_URL": cloud_url,
        "LOCAL_DATABASE_URL": snap["local_database_url"]
        or existing.get("LOCAL_DATABASE_URL")
        or DEFAULTS["LOCAL_DATABASE_URL"],
        "PUSH_SCHEDULE_ENABLED": "1" if body.push_schedule_enabled else "0",
        "PUSH_SCHEDULE_MODE": body.push_schedule_mode,
        "PUSH_SCHEDULE_TIMES": times_csv,
        "PUSH_SCHEDULE_INTERVAL_HOURS": str(body.push_schedule_interval_hours),
    }
    _write_env(values)
    logger.info(
        "cloud_sync_config_saved host=%s port=%s schedule=%s mode=%s times=%s interval_h=%s",
        values["DEPLOY_HOST"],
        values["NEWSC_TUNNEL_LOCAL_PORT"],
        values["PUSH_SCHEDULE_ENABLED"],
        values["PUSH_SCHEDULE_MODE"],
        values["PUSH_SCHEDULE_TIMES"],
        values["PUSH_SCHEDULE_INTERVAL_HOURS"],
    )

    schedule_result: dict[str, Any] | None = None
    if body.apply_schedule:
        schedule_result = _apply_launchd(enabled=body.push_schedule_enabled)

    payload = get_cloud_sync_config(db)
    if schedule_result is not None:
        payload["schedule_apply"] = schedule_result
    return payload


@router.post("/cloud-sync/tunnel")
def ensure_tunnel(db: Session = Depends(get_db)) -> dict[str, Any]:
    if is_cloud_runtime():
        row = enqueue(db, "sync.ensure_tunnel", {})
        db.commit()
        return {
            "ok": True,
            "enqueued": True,
            "outbox_id": row.id if row else None,
            "message": "已入队，等待 Mac Agent 启动隧道",
        }
    if not TUNNEL_SCRIPT.is_file():
        raise HTTPException(500, f"缺少脚本: {TUNNEL_SCRIPT}")
    logger.info("cloud_sync_tunnel_start script=%s", TUNNEL_SCRIPT)
    try:
        proc = subprocess.run(
            ["bash", str(TUNNEL_SCRIPT), "-d"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        logger.error("cloud_sync_tunnel_timeout")
        raise HTTPException(504, "启动隧道超时") from exc
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    cfg = get_cloud_sync_config(db)
    ok = proc.returncode == 0 and bool(cfg.get("tunnel_up"))
    logger.info("cloud_sync_tunnel_done ok=%s rc=%s", ok, proc.returncode)
    return {
        "ok": ok,
        "returncode": proc.returncode,
        "output": out[-4000:],
        "tunnel_up": cfg.get("tunnel_up"),
        "config": cfg,
    }


@router.post("/cloud-sync/push")
def push_to_cloud(
    body: CloudSyncPushIn = CloudSyncPushIn(), db: Session = Depends(get_db)
) -> dict[str, Any]:
    if is_cloud_runtime():
        row = enqueue(db, "sync.push_db", {"dry_run": body.dry_run})
        db.commit()
        return {
            "ok": True,
            "enqueued": True,
            "dry_run": body.dry_run,
            "outbox_id": row.id if row else None,
            "message": "已入队，等待 Mac Agent 执行推库",
        }

    raw = _parse_env_file(CLOUD_ENV)
    if not raw.get("CLOUD_DATABASE_URL", "").strip():
        raise HTTPException(400, "未配置 CLOUD_DATABASE_URL，请先保存同步配置")
    if not PUSH_SCRIPT.is_file():
        raise HTTPException(500, f"缺少脚本: {PUSH_SCRIPT}")

    cmd = ["bash", str(PUSH_SCRIPT)]
    if body.dry_run:
        cmd.append("--dry-run")
    logger.info("cloud_sync_push_start dry_run=%s cmd=%s", body.dry_run, " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        logger.error("cloud_sync_push_timeout dry_run=%s", body.dry_run)
        raise HTTPException(504, "推送超时（可查看 logs/push-db-to-cloud.log）") from exc

    combined = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    ok = proc.returncode == 0
    logger.info(
        "cloud_sync_push_done ok=%s rc=%s dry_run=%s out_len=%d",
        ok,
        proc.returncode,
        body.dry_run,
        len(combined),
    )
    if not ok:
        tip = combined[-1500:] if combined else f"rc={proc.returncode}"
        raise HTTPException(500, f"推送失败：{tip}")
    return {
        "ok": True,
        "dry_run": body.dry_run,
        "returncode": proc.returncode,
        "output": combined[-6000:],
        "last_push": _last_push_info(),
        "config": get_cloud_sync_config(db),
    }


@router.get("/cloud-sync/outbox")
def list_outbox(
    db: Session = Depends(get_db),
    status: str | None = None,
    limit: int = 30,
) -> dict[str, Any]:
    from pipeline.models import CloudOutbox

    q = db.query(CloudOutbox).order_by(CloudOutbox.created_at.desc())
    if status:
        q = q.filter(CloudOutbox.status == status)
    rows = q.limit(max(1, min(limit, 100))).all()
    return {
        "runtime": "cloud" if is_cloud_runtime() else "local",
        "count": len(rows),
        "items": [
            {
                "id": r.id,
                "kind": r.kind,
                "status": r.status,
                "payload": r.payload,
                "error": r.error,
                "result": r.result,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "done_at": r.done_at.isoformat() if r.done_at else None,
            }
            for r in rows
        ],
    }
