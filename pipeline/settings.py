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

    database_url: str = "postgresql+psycopg://expeqiu@/newsc?host=/tmp"
    orch_host: str = "127.0.0.1"
    orch_port: int = 8787
    log_level: str = "INFO"

    ai_mock_mode: bool = True
    ai_provider: str = "mock"
    openclaw_gateway_url: str = "http://127.0.0.1:18789"
    openclaw_token: str = ""

    def resolved_provider(self) -> str:
        if self.ai_mock_mode:
            return "mock"
        return (self.ai_provider or "mock").lower()


@lru_cache
def get_settings() -> Settings:
    return Settings()


def env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}
