from __future__ import annotations

from app.eventing import build_event_log_path, get_run_stamp


def build_log_path(prefix: str, *, log_dir: str = "logs"):
    """Build the per-run log file path for the supplied prefix."""
    return build_event_log_path(log_dir, prefix)
