"""运行时环境：本机 Mac vs 云端副本。"""
from __future__ import annotations

import os


def is_cloud_runtime() -> bool:
    """云端 PM2 / cron 设置 DEPLOY_ENV=cloud；本机开发默认 false。"""
    return (os.getenv("DEPLOY_ENV") or "").strip().lower() == "cloud"
