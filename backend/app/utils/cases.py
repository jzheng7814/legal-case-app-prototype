from __future__ import annotations

__all__ = ["normalize_case_id"]


def normalize_case_id(case_id: str) -> str:
    """Normalize case identifiers for consistent persistence keys."""
    try:
        return str(int(case_id))
    except (TypeError, ValueError):
        return str(case_id)
