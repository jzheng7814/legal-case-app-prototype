from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Optional, Protocol

from app.eventing import get_event_producer

producer = get_event_producer(__name__)


@dataclass(frozen=True)
class StoredCaseDocuments:
    """Container for cached Clearinghouse documents."""

    documents: List[Dict[str, Any]]
    case_title: str
    stored_at: Optional[str] = None


class CaseDocumentStore(Protocol):
    """Interface for persisting documents fetched from Clearinghouse."""

    def get(self, case_id: str) -> Optional[StoredCaseDocuments]:
        """Return the stored documents for a case."""

    def set(self, case_id: str, documents: List[Dict[str, Any]], case_title: str) -> None:
        """Persist the supplied documents for a case."""

    def clear(self, case_id: str) -> None:
        """Remove the cached documents for a case."""


class JsonCaseDocumentStore(CaseDocumentStore):
    """Simple JSON-backed store for caching case documents."""

    def __init__(self, file_path: Path) -> None:
        self._file_path = file_path
        self._lock = RLock()
        self._file_path.parent.mkdir(parents=True, exist_ok=True)

    def get(self, case_id: str) -> Optional[StoredCaseDocuments]:
        key = _normalize_case_id(case_id)
        with self._lock:
            payload = self._load()
            raw_entry = payload.get(key)
        if not isinstance(raw_entry, dict):
            return None
        documents = raw_entry.get("documents")
        case_title = raw_entry.get("case_title")
        stored_at = raw_entry.get("stored_at")
        if not isinstance(documents, list):
            producer.debug("Cached document entry missing documents list", {"case_id": key})
            return None
        if not isinstance(case_title, str) or not case_title.strip():
            producer.debug("Cached document entry missing case title", {"case_id": key})
            return None
        return StoredCaseDocuments(
            documents=documents,
            case_title=case_title.strip(),
            stored_at=stored_at if isinstance(stored_at, str) else None,
        )

    def set(self, case_id: str, documents: List[Dict[str, Any]], case_title: str) -> None:
        if not isinstance(case_title, str) or not case_title.strip():
            raise ValueError("case_title is required when caching case documents.")
        record = {
            "documents": documents,
            "case_title": case_title.strip(),
            "stored_at": datetime.now(timezone.utc).isoformat(),
        }
        key = _normalize_case_id(case_id)
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
            producer.warning(
                "Case document store did not contain an object; resetting",
                {"path": str(self._file_path)},
            )
        except (json.JSONDecodeError, OSError):
            producer.error(
                "Failed to read case document store; resetting",
                {"path": str(self._file_path)},
            )
        return {}

    def _write(self, payload: Dict[str, Any]) -> None:
        tmp_path = self._file_path.with_suffix(".tmp")
        try:
            tmp_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
            tmp_path.replace(self._file_path)
        except OSError:
            producer.error("Failed to persist case document store", {"path": str(self._file_path)})
            raise
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    producer.warning(
                        "Unable to clean up temporary case document store file",
                        {"path": str(tmp_path)},
                    )


def _normalize_case_id(case_id: str) -> str:
    try:
        return str(int(case_id))
    except (TypeError, ValueError):
        return str(case_id)
