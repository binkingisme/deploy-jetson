"""Structured logging setup."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)


def setup_logging(
    level: int = logging.INFO, log_file: Path | None = None
) -> logging.Logger:
    """Configure root logging and return the app logger."""
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=level,
        format=_FORMAT,
        handlers=handlers,
    )

    logger = logging.getLogger("face-ai")
    logger.setLevel(level)
    return logger
