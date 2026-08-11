"""Shared settings for NewsC."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT / ".env"), extra="ignore")

    database_url: str = "postgresql+psycopg://qiubin@/newsc?host=/tmp"
    orch_host: str = "127.0.0.1"
    orch_port: int = 8787
    log_level: str = "INFO"
    orch_api_token: str = ""
    # 空则按 WEB_PORT 自动拼本机 Origin；也可逗号分隔显式覆盖
    orch_cors_origins: str = ""
    web_port: int = 3000

    ai_mock_mode: bool = True
    ai_provider: str = "mock"
    openclaw_gateway_url: str = "http://127.0.0.1:18789"
    openclaw_token: str = ""
    ai_fallback_strict: bool = False
    ai_job_max_attempts: int = 3
    ai_job_stale_running_sec: int = 900

    # MiniMax（OpenAI 兼容；国内默认 minimaxi.com）
    # Coding Plan Key（sk-cp-）优先于普通 MINIMAX_API_KEY
    minimax_coding_api_key: str = ""
    minimax_api_key: str = ""
    minimax_base_url: str = "https://api.minimaxi.com/v1"
    minimax_model: str = "MiniMax-M3"

    # 日报 HTML vault（相对仓库根或绝对路径；见 digest-sources.yml）
    digest_sources_file: str = "digest-sources.yml"

    def resolved_minimax_api_key(self) -> str:
        return (self.minimax_coding_api_key or self.minimax_api_key or "").strip()

    def resolved_provider(self) -> str:
        if self.ai_mock_mode:
            return "mock"
        return (self.ai_provider or "mock").lower()

    def cors_origins_list(self) -> list[str]:
        """本机 Web Origin；显式 ORCH_CORS_ORIGINS 优先，并始终补上当前 WEB_PORT。"""
        port = int(self.web_port or 3000)
        auto = [
            f"http://127.0.0.1:{port}",
            f"http://localhost:{port}",
        ]
        if port != 3000:
            auto.extend(["http://127.0.0.1:3000", "http://localhost:3000"])
        raw = (self.orch_cors_origins or "").strip()
        explicit = [o.strip() for o in raw.split(",") if o.strip()] if raw else []
        seen: set[str] = set()
        out: list[str] = []
        for o in explicit + auto:
            if o not in seen:
                seen.add(o)
                out.append(o)
        return out


@lru_cache
def get_settings() -> Settings:
    return Settings()


def env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}
