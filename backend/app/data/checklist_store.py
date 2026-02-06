from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

from app.eventing import get_event_producer
from app.db.models import ChecklistItem as ChecklistItemRow
from app.db.models import ChecklistRecord
from app.db.session import get_session
from app.schemas.checklists import EvidenceCollection, EvidenceItem, EvidencePointer

producer = get_event_producer(__name__)

DocumentChecklistPayload = EvidenceCollection

_CHECKLIST_STORE_VERSION = "evidence-items-v1"


@dataclass(frozen=True)
class StoredDocumentChecklist:
    """Container for a stored checklist record."""

    items: DocumentChecklistPayload
    version: str = _CHECKLIST_STORE_VERSION


class DocumentChecklistStore(Protocol):
    """Interface that supports persisting checklist results."""

    def get(self, case_id: str) -> Optional[StoredDocumentChecklist]:
        """Return the stored checklist for a case."""

    def set(
        self,
        case_id: str,
        *,
        items: DocumentChecklistPayload,
        version: str,
    ) -> None:
        """Persist a checklist for a case."""

    def clear(self, case_id: str) -> None:
        """Remove cached checklist data for a case."""


class SqlDocumentChecklistStore(DocumentChecklistStore):
    """SQLite-backed checklist persistence."""

    def __init__(self) -> None:
        self._session_factory = get_session

    def get(self, case_id: str) -> Optional[StoredDocumentChecklist]:
        key = _normalize_case_id(case_id)
        session = self._session_factory()
        try:
            record = session.get(ChecklistRecord, key)
            if record is None:
                return None
            if record.version != _CHECKLIST_STORE_VERSION:
                producer.debug(
                    "Checklist store entry has mismatched version",
                    {"case_id": key, "found": record.version, "expected": _CHECKLIST_STORE_VERSION},
                )
                return None
            rows = (
                session.query(ChecklistItemRow)
                .filter(ChecklistItemRow.case_id == key)
                .order_by(ChecklistItemRow.item_index.asc())
                .all()
            )
            items = [
                EvidenceItem(
                    bin_id=row.bin_id,
                    value=row.value,
                    evidence=EvidencePointer(
                        document_id=row.document_id,
                        location=row.location,
                        start_offset=row.start_offset,
                        end_offset=row.end_offset,
                        text=row.text,
                        verified=bool(row.verified) if row.verified is not None else True,
                    ),
                )
                for row in rows
            ]
            return StoredDocumentChecklist(items=EvidenceCollection(items=items), version=record.version)
        finally:
            session.close()

    def set(
        self,
        case_id: str,
        *,
        items: DocumentChecklistPayload,
        version: str,
    ) -> None:
        key = _normalize_case_id(case_id)
        session = self._session_factory()
        try:
            session.query(ChecklistItemRow).filter(ChecklistItemRow.case_id == key).delete()
            session.query(ChecklistRecord).filter(ChecklistRecord.case_id == key).delete()

            session.add(ChecklistRecord(case_id=key, version=version))
            for index, item in enumerate(items.items):
                session.add(
                    ChecklistItemRow(
                        case_id=key,
                        item_index=index,
                        bin_id=item.bin_id,
                        value=item.value,
                        document_id=item.evidence.document_id,
                        location=item.evidence.location,
                        start_offset=item.evidence.start_offset,
                        end_offset=item.evidence.end_offset,
                        text=item.evidence.text,
                        verified=item.evidence.verified,
                    )
                )
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def clear(self, case_id: str) -> None:
        key = _normalize_case_id(case_id)
        session = self._session_factory()
        try:
            session.query(ChecklistItemRow).filter(ChecklistItemRow.case_id == key).delete()
            session.query(ChecklistRecord).filter(ChecklistRecord.case_id == key).delete()
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def _normalize_case_id(case_id: str) -> str:
    """Ensure case identifiers serialize consistently."""
    try:
        # Preserve numeric IDs as canonical decimal strings for compatibility with JSON object keys.
        return str(int(case_id))
    except (TypeError, ValueError):
        return str(case_id)
