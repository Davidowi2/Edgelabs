"""Structured logging setup."""

from __future__ import annotations

import sys
from typing import Optional

from loguru import logger


def setup_logging(level: str = "INFO", log_file: Optional[str] = None) -> None:
    logger.remove()
    logger.add(
        sys.stdout,
        level=level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | {message}",
    )
    if log_file:
        logger.add(
            log_file,
            level=level,
            rotation="10 MB",
            encoding="utf-8",
        )
