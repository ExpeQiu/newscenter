"""Structured logging helpers for intelligence."""
from __future__ import annotations

import logging
from typing import Any


def get_logger(name: str = "newsc.intelligence") -> logging.Logger:
    return logging.getLogger(name)


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    parts = " ".join(f"{k}={v}" for k, v in fields.items() if v is not None)
    logger.info("%s %s", event, parts)
