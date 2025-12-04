from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Optional, Protocol

from pydantic import ValidationError

from app.schemas.checklists import EvidenceCollection

logger = logging.getLogger(__name__)

DocumentChecklistPayload = EvidenceCollection

_CHECKLIST_STORE_VERSION = "evidence-items-v1"


@dataclass(frozen=True)
class StoredUserChecklistItem:
    """User-authored checklist entry stored outside the AI extraction results."""

    id: str
    category_id: str
    value: str
    document_id: Optional[int]
    start_offset: Optional[int]
    end_offset: Optional[int]


@dataclass(frozen=True)
class StoredDocumentChecklist:
    """Container for a stored checklist record."""

    signature: str
    items: DocumentChecklistPayload
    user_items: list[StoredUserChecklistItem]
    version: str = _CHECKLIST_STORE_VERSION


class DocumentChecklistStore(Protocol):
    """Interface that supports persisting checklist results."""

    def get(self, case_id: str, *, signature: Optional[str] = None) -> Optional[StoredDocumentChecklist]:
        """Return the stored checklist for a case, optionally validating a signature."""

    def set(
        self,
        case_id: str,
        *,
        signature: str,
        items: DocumentChecklistPayload,
        user_items: Optional[list[StoredUserChecklistItem]] = None,
    ) -> None:
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
            version = raw_entry.get("version")
            items = raw_entry.get("items")
            user_items = raw_entry.get("userItems") or raw_entry.get("user_items") or []
        if not isinstance(stored_signature, str) or items is None:
            logger.debug("Checklist store entry for case %s missing expected structure.", key)
            return None
        if version and version != _CHECKLIST_STORE_VERSION:
            logger.debug(
                "Checklist store entry for case %s has mismatched version (found=%s, expected=%s).",
                key,
                version,
                _CHECKLIST_STORE_VERSION,
            )
            return None
        collection = _coerce_to_collection(items)
        if collection is None:
            logger.debug("Checklist store entry for case %s failed validation.", key)
            return None
        record = StoredDocumentChecklist(
            signature=stored_signature,
            items=collection,
            user_items=_coerce_user_items(user_items),
            version=version or _CHECKLIST_STORE_VERSION,
        )
        if signature and record.signature != signature:
            logger.debug(
                "Checklist store signature mismatch for case %s (expected %s, found %s).",
                key,
                signature,
                record.signature,
            )
            return None
        return record

    def set(
        self,
        case_id: str,
        *,
        signature: str,
        items: DocumentChecklistPayload,
        user_items: Optional[list[StoredUserChecklistItem]] = None,
    ) -> None:
        key = _normalize_case_id(case_id)
        record = {
            "signature": signature,
            "items": items.model_dump(by_alias=True, exclude_none=True),
            "version": _CHECKLIST_STORE_VERSION,
            "userItems": [
                {
                    "id": entry.id,
                    "categoryId": entry.category_id,
                    "value": entry.value,
                    "documentId": entry.document_id,
                    "startOffset": entry.start_offset,
                    "endOffset": entry.end_offset,
                }
                for entry in (user_items or [])
            ],
        }
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


def _coerce_to_collection(raw_items: Any) -> Optional[EvidenceCollection]:
    if isinstance(raw_items, EvidenceCollection):
        return raw_items

    payload: Dict[str, Any]
    if isinstance(raw_items, dict):
        if "items" in raw_items:
            payload = raw_items
        else:
            entries = []
            for value in raw_items.values():
                if not isinstance(value, dict):
                    return None
                entries.append(value)
            payload = {"items": entries}
    elif isinstance(raw_items, list):
        payload = {"items": raw_items}
    else:
        return None

    try:
        return EvidenceCollection.model_validate(payload)
    except ValidationError:
        logger.debug("Evidence collection payload failed validation.")
        return None


def _normalize_case_id(case_id: str) -> str:
    """Ensure case identifiers serialize consistently."""
    try:
        # Preserve numeric IDs as canonical decimal strings for compatibility with JSON object keys.
        return str(int(case_id))
    except (TypeError, ValueError):
        return str(case_id)


def _coerce_user_items(raw_items: Any) -> list[StoredUserChecklistItem]:
    if not isinstance(raw_items, list):
        return []
    results: list[StoredUserChecklistItem] = []
    for entry in raw_items:
        if not isinstance(entry, dict):
            continue
        item_id = entry.get("id")
        category_id = entry.get("category_id") or entry.get("categoryId")
        value = entry.get("value")
        document_id = entry.get("document_id") or entry.get("documentId")
        start_offset = entry.get("start_offset") or entry.get("startOffset")
        end_offset = entry.get("end_offset") or entry.get("endOffset")
        if not isinstance(item_id, str) or not isinstance(category_id, str) or not isinstance(value, str):
            continue
        doc_id_int: Optional[int]
        if document_id is None:
            doc_id_int = None
        else:
            try:
                doc_id_int = int(document_id)
            except (TypeError, ValueError):
                doc_id_int = None
        start_int = _coerce_optional_int(start_offset)
        end_int = _coerce_optional_int(end_offset)
        results.append(
            StoredUserChecklistItem(
                id=item_id,
                category_id=category_id,
                value=value,
                document_id=doc_id_int,
                start_offset=start_int,
                end_offset=end_int,
            )
        )
    return results


def _coerce_optional_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed
