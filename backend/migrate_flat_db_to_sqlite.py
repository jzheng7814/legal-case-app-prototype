#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from app.db.models import CaseDocument, CaseRecord, ChecklistItem, ChecklistRecord
from app.db.session import get_session, init_db


BASE_DIR = Path(__file__).resolve().parent
FLAT_DB_DIR = BASE_DIR / "app" / "data" / "flat_db"
CASE_DOCS_PATH = FLAT_DB_DIR / "case_documents.json"
CHECKLIST_PATH = FLAT_DB_DIR / "document_checklist_items_v2.json"


def _normalize_case_id(case_id: str) -> str:
    try:
        return str(int(case_id))
    except (TypeError, ValueError):
        return str(case_id)


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing source file: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Expected object at root of {path}")
    return raw


def _require_dict(value: Any, context: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Expected object for {context}")
    return value


def _require_list(value: Any, context: str) -> List[Any]:
    if not isinstance(value, list):
        raise ValueError(f"Expected list for {context}")
    return value


def _parse_int(value: Any, context: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"Expected integer for {context}") from None


def _parse_str(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Expected non-empty string for {context}")
    return value.strip()


def _parse_optional_int(value: Any, context: str) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"Expected integer for {context}") from None


def _parse_optional_bool(value: Any, context: str) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    raise ValueError(f"Expected boolean for {context}")


def _iter_documents(payload: Dict[str, Any]) -> Iterable[Tuple[str, Dict[str, Any]]]:
    for case_id, record in payload.items():
        record = _require_dict(record, f"case_documents[{case_id}]")
        yield _normalize_case_id(case_id), record


def _iter_checklists(payload: Dict[str, Any]) -> Iterable[Tuple[str, Dict[str, Any]]]:
    for case_id, record in payload.items():
        record = _require_dict(record, f"checklists[{case_id}]")
        yield _normalize_case_id(case_id), record


def migrate() -> None:
    case_docs_payload = _load_json(CASE_DOCS_PATH)
    checklist_payload = _load_json(CHECKLIST_PATH)

    init_db()
    session = get_session()
    try:
        if session.query(CaseRecord).first() or session.query(ChecklistRecord).first():
            raise RuntimeError("Database already contains data; aborting migration.")

        for case_id, record in _iter_documents(case_docs_payload):
            case_title = _parse_str(record.get("case_title"), f"case_documents[{case_id}].case_title")
            documents = _require_list(record.get("documents"), f"case_documents[{case_id}].documents")
            stored_at = record.get("stored_at")
            if stored_at is not None and not isinstance(stored_at, str):
                raise ValueError(f"Expected stored_at to be string for case_documents[{case_id}]")

            session.add(CaseRecord(case_id=case_id, case_title=case_title, stored_at=stored_at))

            for idx, doc in enumerate(documents):
                doc = _require_dict(doc, f"case_documents[{case_id}].documents[{idx}]")
                doc_id = _parse_int(doc.get("id"), f"case_documents[{case_id}].documents[{idx}].id")
                content = doc.get("content")
                if not isinstance(content, str):
                    raise ValueError(
                        f"Expected string content for case_documents[{case_id}].documents[{idx}].content"
                    )
                session.add(
                    CaseDocument(
                        case_id=case_id,
                        document_id=doc_id,
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
                        content=content,
                    )
                )

        for case_id, record in _iter_checklists(checklist_payload):
            version = record.get("version")
            if not version:
                raise ValueError(f"Missing version for checklists[{case_id}]")
            if not isinstance(version, str):
                raise ValueError(f"Expected version to be string for checklists[{case_id}]")

            raw_items = record.get("items")
            if isinstance(raw_items, dict):
                raw_items = raw_items.get("items")
            items = _require_list(raw_items, f"checklists[{case_id}].items")

            session.add(ChecklistRecord(case_id=case_id, version=version))

            for index, item in enumerate(items):
                item = _require_dict(item, f"checklists[{case_id}].items[{index}]")
                bin_id = item.get("binId") or item.get("bin_id")
                value = item.get("value")
                evidence = _require_dict(item.get("evidence"), f"checklists[{case_id}].items[{index}].evidence")

                if not isinstance(bin_id, str) or not bin_id.strip():
                    raise ValueError(f"Missing bin_id for checklists[{case_id}].items[{index}]")
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"Missing value for checklists[{case_id}].items[{index}]")

                document_id = evidence.get("documentId") or evidence.get("document_id")
                if document_id is None:
                    raise ValueError(f"Missing document_id for checklists[{case_id}].items[{index}]")
                document_id = _parse_int(document_id, f"checklists[{case_id}].items[{index}].document_id")

                session.add(
                    ChecklistItem(
                        case_id=case_id,
                        item_index=index,
                        bin_id=bin_id,
                        value=value,
                        document_id=document_id,
                        location=evidence.get("location"),
                        start_offset=_parse_optional_int(
                            evidence.get("startOffset") or evidence.get("start_offset"),
                            f"checklists[{case_id}].items[{index}].start_offset",
                        ),
                        end_offset=_parse_optional_int(
                            evidence.get("endOffset") or evidence.get("end_offset"),
                            f"checklists[{case_id}].items[{index}].end_offset",
                        ),
                        text=evidence.get("text"),
                        verified=_parse_optional_bool(
                            evidence.get("verified"),
                            f"checklists[{case_id}].items[{index}].verified",
                        ),
                    )
                )

        session.commit()
        print("Migration complete.")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    migrate()
