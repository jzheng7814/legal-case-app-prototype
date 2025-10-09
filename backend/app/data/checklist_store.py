from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Optional, Protocol

logger = logging.getLogger(__name__)

DocumentChecklistPayload = Dict[str, Dict[str, Any]]


@dataclass(frozen=True)
class StoredDocumentChecklist:
    """Container for a stored checklist record."""

    signature: str
    items: DocumentChecklistPayload


class DocumentChecklistStore(Protocol):
    """Interface that supports persisting checklist results."""

    def get(self, case_id: str, *, signature: Optional[str] = None) -> Optional[StoredDocumentChecklist]:
        """Return the stored checklist for a case, optionally validating a signature."""

    def set(self, case_id: str, *, signature: str, items: DocumentChecklistPayload) -> None:
        """Persist a checklist for a case."""

    def clear(self, case_id: str) -> None:
        """Remove cached checklist data for a case."""


class JsonDocumentChecklistStore(DocumentChecklistStore):
    """File-based checklist persistence with a single JSON document."""

    def __init__(self, file_path: Path) -> None:
        self._file_path = file_path
        self._lock = RLock()
        self._file_path.parent.mkdir(parents=True, exist_ok=True)

    def get(self, case_id: str, *, signature: Optional[str] = None) -> Optional[StoredDocumentChecklist]:
        key = _normalize_case_id(case_id)
        with self._lock:
            payload = self._load()
            raw_entry = payload.get(key)
            if not isinstance(raw_entry, dict):
                return None
            stored_signature = raw_entry.get("signature")
            items = raw_entry.get("items")
        if not isinstance(stored_signature, str) or not isinstance(items, dict):
            logger.debug("Checklist store entry for case %s missing expected structure.", key)
            return None
        record = StoredDocumentChecklist(signature=stored_signature, items=items)
        if signature and record.signature != signature:
            logger.debug(
                "Checklist store signature mismatch for case %s (expected %s, found %s).",
                key,
                signature,
                record.signature,
            )
            return None
        return record

    def set(self, case_id: str, *, signature: str, items: DocumentChecklistPayload) -> None:
        key = _normalize_case_id(case_id)
        record = {"signature": signature, "items": items}
        with self._lock:
            payload = self._load()
            payload[key] = record
            self._write(payload)

    def clear(self, case_id: str) -> None:
        key = _normalize_case_id(case_id)
        with self._lock:
            payload = self._load()
            if key in payload:
                payload.pop(key, None)
                self._write(payload)

    def _load(self) -> Dict[str, Any]:
        if not self._file_path.exists():
            return {}
        try:
            data = json.loads(self._file_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
            logger.warning("Checklist store file %s did not contain an object. Resetting.", self._file_path)
        except (json.JSONDecodeError, OSError):
            logger.exception("Failed to read checklist store from %s. Resetting.", self._file_path)
        return {}

    def _write(self, payload: Dict[str, Any]) -> None:
        tmp_path = self._file_path.with_suffix(".tmp")
        try:
            tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
            tmp_path.replace(self._file_path)
        except OSError:
            logger.exception("Failed to persist checklist store to %s.", self._file_path)
            raise
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    logger.warning("Unable to clean up temporary checklist store file %s.", tmp_path)


def _normalize_case_id(case_id: str) -> str:
    """Ensure case identifiers serialize consistently."""
    try:
        # Preserve numeric IDs as canonical decimal strings for compatibility with JSON object keys.
        return str(int(case_id))
    except (TypeError, ValueError):
        return str(case_id)
