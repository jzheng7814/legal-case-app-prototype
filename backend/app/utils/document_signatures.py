from __future__ import annotations

import hashlib
from typing import Iterable, Mapping, Any

from app.utils.cases import normalize_case_id

__all__ = ["compute_documents_signature"]


def compute_documents_signature(case_id: str, payloads: Iterable[Mapping[str, Any]]) -> str:
    """Produce a stable hash for a bundle of document payloads."""
    normalized_case = normalize_case_id(case_id)
    digest = hashlib.sha256(normalized_case.encode("utf-8"))
    payload_list = list(payloads)
    payload_list.sort(key=lambda item: str(item.get("id", "")))
    for payload in payload_list:
        digest.update(str(payload.get("id", "")).encode("utf-8"))
        digest.update((payload.get("title") or "").encode("utf-8"))
        digest.update((payload.get("type") or "").encode("utf-8"))
        digest.update((payload.get("text") or payload.get("content") or "").encode("utf-8"))
    return digest.hexdigest()
