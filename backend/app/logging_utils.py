from __future__ import annotations

import logging
from datetime import datetime
from functools import lru_cache
from pathlib import Path


def _logs_root() -> Path:
    root = Path(__file__).resolve().parents[1] / "logs"
    root.mkdir(parents=True, exist_ok=True)
    return root


@lru_cache(maxsize=1)
def get_run_stamp() -> str:
    """Return the timestamp identifier for the current backend run."""
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def build_log_path(prefix: str) -> Path:
    """Build the log file path for the current run and supplied prefix."""
    return _logs_root() / f"{prefix}-{get_run_stamp()}.log"


def configure_file_logger(logger_name: str, *, prefix: str, level: int = logging.INFO) -> logging.Logger:
    """
    Ensure that a dedicated file logger exists for this backend run.

    Each call returns the same logger instance configured with a FileHandler
    that writes to a timestamped log file unique to this process.
    """
    logger = logging.getLogger(logger_name)
    if not any(isinstance(handler, logging.FileHandler) for handler in logger.handlers):
        handler = logging.FileHandler(build_log_path(prefix))
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(level)
        logger.propagate = False
    return logger
