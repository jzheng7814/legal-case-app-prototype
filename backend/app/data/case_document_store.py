from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol

from app.db.models import CaseDocument, CaseRecord
from app.db.session import get_session


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


class SqlCaseDocumentStore(CaseDocumentStore):
    """SQLite-backed store for caching case documents."""

    def __init__(self) -> None:
        self._session_factory = get_session

    def get(self, case_id: str) -> Optional[StoredCaseDocuments]:
        key = _normalize_case_id(case_id)
        session = self._session_factory()
        try:
            case = session.get(CaseRecord, key)
            if case is None:
                return None
            docs = (
                session.query(CaseDocument)
                .filter(CaseDocument.case_id == key)
                .order_by(CaseDocument.document_id.asc())
                .all()
            )
            if not docs:
                return None
            documents: List[Dict[str, Any]] = []
            for doc in docs:
                documents.append(
                    {
                        "id": doc.document_id,
                        "title": doc.title,
                        "type": doc.type,
                        "description": doc.description,
                        "source": doc.source,
                        "court": doc.court,
                        "state": doc.state,
                        "ecf_number": doc.ecf_number,
                        "file_url": doc.file_url,
                        "external_url": doc.external_url,
                        "clearinghouse_link": doc.clearinghouse_link,
                        "text_url": doc.text_url,
                        "date": doc.date,
                        "date_is_estimate": doc.date_is_estimate,
                        "date_not_available": doc.date_not_available,
                        "is_docket": doc.is_docket,
                        "content": doc.content,
                    }
                )
            return StoredCaseDocuments(
                documents=documents,
                case_title=case.case_title,
                stored_at=case.stored_at,
            )
        finally:
            session.close()

    def set(self, case_id: str, documents: List[Dict[str, Any]], case_title: str) -> None:
        if not isinstance(case_title, str) or not case_title.strip():
            raise ValueError("case_title is required when caching case documents.")
        key = _normalize_case_id(case_id)
        session = self._session_factory()
        try:
            session.query(CaseDocument).filter(CaseDocument.case_id == key).delete()
            session.query(CaseRecord).filter(CaseRecord.case_id == key).delete()

            record = CaseRecord(
                case_id=key,
                case_title=case_title.strip(),
                stored_at=datetime.now(timezone.utc).isoformat(),
            )
            session.add(record)

            for doc in documents:
                doc_id = doc.get("id")
                content = doc.get("content")
                if doc_id is None or content is None:
                    raise ValueError("Document entries must include id and content fields.")
                session.add(
                    CaseDocument(
                        case_id=key,
                        document_id=int(doc_id),
                        title=doc.get("title"),
                        type=doc.get("type"),
                        description=doc.get("description"),
                        source=doc.get("source"),
                        court=doc.get("court"),
                        state=doc.get("state"),
                        ecf_number=doc.get("ecf_number"),
                        file_url=doc.get("file_url"),
                        external_url=doc.get("external_url"),
                        clearinghouse_link=doc.get("clearinghouse_link"),
                        text_url=doc.get("text_url"),
                        date=doc.get("date"),
                        date_is_estimate=doc.get("date_is_estimate"),
                        date_not_available=doc.get("date_not_available"),
                        is_docket=bool(doc.get("is_docket") or False),
                        content=str(content),
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
            session.query(CaseDocument).filter(CaseDocument.case_id == key).delete()
            session.query(CaseRecord).filter(CaseRecord.case_id == key).delete()
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def _normalize_case_id(case_id: str) -> str:
    try:
        return str(int(case_id))
    except (TypeError, ValueError):
        return str(case_id)
