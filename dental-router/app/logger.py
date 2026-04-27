"""Centralised logging configuration."""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_FILE = LOG_DIR / "dental_router.log"


def setup_logger(name: str = "dental_router") -> logging.Logger:
    """Create (or retrieve) a named logger with file + console handlers."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    log = logging.getLogger(name)
    if log.handlers:
        return log

    log.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Rotating file handler – 5 MB × 3 backups
    fh = logging.handlers.RotatingFileHandler(
        LOG_FILE,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    log.addHandler(fh)
    log.addHandler(ch)
    return log


logger: logging.Logger = setup_logger()
