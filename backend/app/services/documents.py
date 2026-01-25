from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Iterable, List, Optional

from fastapi import HTTPException

from app.core.config import get_settings
from app.data.case_document_store import CaseDocumentStore, JsonCaseDocumentStore
from app.eventing import get_event_producer
from app.schemas.documents import Document, DocumentMetadata
from app.services.clearinghouse import (
    ClearinghouseClient,
    ClearinghouseError,
    ClearinghouseNotConfigured,
    ClearinghouseNotFound,
)

producer = get_event_producer(__name__)

_DEFAULT_CASE_ID = "-1"

_settings = get_settings()
_DATA_ROOT = Path(__file__).resolve().parent.parent / _settings.document_root
_CASE_STORE_PATH = Path(__file__).resolve().parents[1] / "data" / "flat_db" / "case_documents.json"
_CASE_STORE: CaseDocumentStore = JsonCaseDocumentStore(_CASE_STORE_PATH)

_CASE_CACHE: Dict[str, List[Document]] = {}
_CASE_TITLE_CACHE: Dict[str, str] = {}
_CASE_CACHE_LOCK = RLock()


@lru_cache
def _load_catalog() -> Dict[str, Any]:
    catalog_path = _DATA_ROOT / "catalog.json"
    if not catalog_path.exists():
        raise RuntimeError(f"Document catalog not found at {catalog_path}")
    with catalog_path.open("r", encoding="utf-8") as infile:
        return json.load(infile)


def list_documents(case_id: str) -> List[Document]:
    normalized = _normalize_case_id(case_id)

    catalog_payload = _load_catalog_documents(normalized)
    if catalog_payload is not None:
        catalog_documents, case_title = catalog_payload
        ordered = _sort_documents(catalog_documents)
        _remember_documents(normalized, ordered, case_title)
        try:
            _CASE_STORE.set(normalized, [doc.model_dump(mode="json") for doc in ordered], case_title)
        except Exception:  # pylint: disable=broad-except
            producer.error("Failed to persist catalog documents", {"case_id": normalized})
        return _clone_documents(ordered)

    cached = _get_cached_documents(normalized)
    if cached is not None:
        producer.info("Serving cached documents", {"case_id": normalized})
        return cached

    producer.info("Fetching documents from Clearinghouse", {"case_id": normalized})
    try:
        documents, case_title = _fetch_remote_documents(normalized)
    except ClearinghouseNotConfigured as exc:
        producer.warning("Clearinghouse API key not configured", {"case_id": normalized})
        cached = _get_cached_documents(normalized)
        if cached:
            return cached
        raise HTTPException(
            status_code=503, detail="Clearinghouse API key has not been configured on the server."
        ) from exc
    except ClearinghouseNotFound as exc:
        cached = _get_cached_documents(normalized)
        if cached:
            return cached
        raise HTTPException(status_code=404, detail=f"Case '{normalized}' was not found on Clearinghouse.") from exc
    except ClearinghouseError as exc:
        producer.warning(
            "Clearinghouse request failed",
            {"case_id": normalized, "error": str(exc)},
        )
        cached = _get_cached_documents(normalized)
        if cached:
            return cached
        raise HTTPException(
            status_code=502, detail="Failed to retrieve documents from Clearinghouse. Please try again later."
        ) from exc

    ordered = _sort_documents(documents)
    _remember_documents(normalized, ordered, case_title)
    return _clone_documents(ordered)


def list_cached_documents(case_id: str) -> List[Document]:
    """Return cached/stored documents for a case without hitting external sources."""
    normalized = _normalize_case_id(case_id)
    cached = _get_cached_documents(normalized)
    if cached is not None:
        return _sort_documents(cached)
    return []


def get_document(case_id: str, document_id: str) -> Document:
    normalized = _normalize_case_id(case_id)
    documents = _get_cached_documents(normalized)
    if documents is None:
        documents = list_documents(normalized)
    for document in documents:
        if document.id == document_id:
            return document
    raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found for case '{case_id}'")


def get_document_metadata(case_id: str) -> List[DocumentMetadata]:
    normalized = _normalize_case_id(case_id)
    documents = _get_cached_documents(normalized)
    if documents is None:
        documents = list_documents(normalized)
    return [
        DocumentMetadata(
            id=doc.id,
            title=doc.title,
            type=doc.type,
            description=doc.description,
            source=doc.source,
        )
        for doc in documents
    ]


def get_case_title(case_id: str) -> Optional[str]:
    """Return the cached case title if available."""
    normalized = _normalize_case_id(case_id)
    with _CASE_CACHE_LOCK:
        cached = _CASE_TITLE_CACHE.get(normalized)
        if cached:
            return cached

    stored = _CASE_STORE.get(normalized)
    if stored is None:
        return None

    title = stored.case_title
    with _CASE_CACHE_LOCK:
        _CASE_TITLE_CACHE[normalized] = title
    return title


def _require_case_title(source: Optional[str], documents: Iterable[Document]) -> str:
    if isinstance(source, str) and source.strip():
        return source.strip()
    for doc in documents:
        if isinstance(doc.description, str) and doc.description.strip():
            return doc.description.strip()
        if isinstance(doc.title, str) and doc.title.strip():
            return doc.title.strip()
    raise HTTPException(status_code=500, detail="Case title could not be determined from the provided documents.")


def _load_catalog_documents(case_id: str) -> Optional[tuple[List[Document], str]]:
    catalog = _load_catalog()
    case_entry = catalog.get("cases", {}).get(case_id)
    if not case_entry:
        return None

    documents: List[Document] = []
    case_title = case_entry.get("title")
    for item in case_entry.get("documents", []):
        content = _load_document_text(item["filename"])
        try:
            doc_id = int(item["id"])
        except (TypeError, ValueError, KeyError) as exc:
            raise HTTPException(status_code=500, detail="Invalid demo document identifier") from exc
        documents.append(
            Document(
                id=doc_id,
                title=item.get("title") or item.get("name") or f"Document {doc_id}",
                type=item.get("type"),
                description=item.get("description"),
                source="demo",
                content=content,
            )
        )
    resolved_title = _require_case_title(case_title, documents)
    return documents, resolved_title


def _fetch_remote_documents(case_id: str) -> tuple[List[Document], str]:
    client = _get_clearinghouse_client()
    documents, case_title = client.fetch_case_documents(case_id)
    resolved_title = _require_case_title(case_title, documents)
    try:
        _CASE_STORE.set(case_id, [doc.model_dump(mode="json") for doc in documents], resolved_title)
    except Exception:  # pylint: disable=broad-except
        producer.error("Failed to persist Clearinghouse documents", {"case_id": case_id})
    return documents, resolved_title


@lru_cache
def _get_clearinghouse_client() -> ClearinghouseClient:
    api_key = _settings.clearinghouse_api_key
    if not api_key:
        raise ClearinghouseNotConfigured("Clearinghouse API key is not configured.")
    return ClearinghouseClient(api_key=api_key)


def _load_document_text(filename: str) -> str:
    doc_path = _DATA_ROOT / filename
    if not doc_path.exists():
        raise HTTPException(status_code=404, detail=f"Document file '{filename}' missing on server")
    with doc_path.open("r", encoding="utf-8") as infile:
        return infile.read()


def _remember_documents(case_id: str, documents: Iterable[Document], case_title: str) -> None:
    with _CASE_CACHE_LOCK:
        _CASE_CACHE[case_id] = _clone_documents(list(documents))
        _CASE_TITLE_CACHE[case_id] = case_title


def _get_cached_documents(case_id: str) -> Optional[List[Document]]:
    with _CASE_CACHE_LOCK:
        cached = _CASE_CACHE.get(case_id)
        cached_title = _CASE_TITLE_CACHE.get(case_id)
    if cached is not None:
        if cached_title:
            with _CASE_CACHE_LOCK:
                _CASE_TITLE_CACHE[case_id] = cached_title
        return _clone_documents(cached)

    stored = _CASE_STORE.get(case_id)
    if stored is None:
        return None

    documents: List[Document] = []
    for item in stored.documents:
        if isinstance(item, dict):
            working = dict(item)
            if "title" not in working and "name" in working:
                working["title"] = working.pop("name")
            if "id" in working and not isinstance(working["id"], int):
                try:
                    working["id"] = int(str(working["id"]).strip())
                except (TypeError, ValueError):
                    producer.warning(
                        "Unable to coerce cached document id to integer",
                        {"case_id": case_id, "document_id": working["id"]},
                    )
                    continue
            item = working
        documents.append(Document.model_validate(item))
    ordered = _sort_documents(documents)
    _remember_documents(case_id, ordered, stored.case_title)
    return _clone_documents(ordered)


def _clone_documents(documents: Iterable[Document]) -> List[Document]:
    return [Document.model_validate(doc.model_dump(mode="python")) for doc in documents]


def _normalize_case_id(case_id: str) -> str:
    try:
        return str(int(case_id))
    except (TypeError, ValueError):
        return str(case_id)


def _parse_ecf_key(raw_value: Optional[str]) -> tuple[int, int, object]:
    if raw_value is None:
        return (1, 1, "")
    text = str(raw_value).strip()
    if not text:
        return (1, 1, "")
    try:
        number = int(text)
        return (0, 0, number)
    except (TypeError, ValueError):
        return (0, 1, text)


def _document_sort_key(document: Document) -> tuple:
    ecf_flags = _parse_ecf_key(document.ecf_number)
    # Place docket first, then ECF-bearing documents, then remainder by id.
    return (
        0 if document.is_docket else 1,
        ecf_flags[0],
        ecf_flags[1],
        ecf_flags[2],
        document.id,
    )


def _sort_documents(documents: List[Document]) -> List[Document]:
    return sorted(list(documents), key=_document_sort_key)
