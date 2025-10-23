from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Iterable, List, Optional

from fastapi import HTTPException

from app.core.config import get_settings
from app.data.case_document_store import CaseDocumentStore, JsonCaseDocumentStore
from app.schemas.documents import Document, DocumentMetadata
from app.services.clearinghouse import (
    ClearinghouseClient,
    ClearinghouseError,
    ClearinghouseNotConfigured,
    ClearinghouseNotFound,
)

logger = logging.getLogger(__name__)

_DEFAULT_CASE_ID = "-1"

_settings = get_settings()
_DATA_ROOT = Path(__file__).resolve().parent.parent / _settings.document_root
_CASE_STORE_PATH = Path(__file__).resolve().parents[1] / "data" / "flat_db" / "case_documents.json"
_CASE_STORE: CaseDocumentStore = JsonCaseDocumentStore(_CASE_STORE_PATH)

_CASE_CACHE: Dict[str, List[Document]] = {}
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

    catalog_documents = _load_catalog_documents(normalized)
    if catalog_documents is not None:
        _remember_documents(normalized, catalog_documents)
        return _clone_documents(catalog_documents)

    try:
        documents = _fetch_remote_documents(normalized)
    except ClearinghouseNotConfigured as exc:
        logger.warning("Clearinghouse API key not configured; cannot fetch case %s.", normalized)
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
        logger.warning("Clearinghouse request failed for case %s: %s", normalized, exc)
        cached = _get_cached_documents(normalized)
        if cached:
            return cached
        raise HTTPException(
            status_code=502, detail="Failed to retrieve documents from Clearinghouse. Please try again later."
        ) from exc

    return _clone_documents(documents)


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


def _load_catalog_documents(case_id: str) -> Optional[List[Document]]:
    catalog = _load_catalog()
    case_entry = catalog.get("cases", {}).get(case_id)
    if not case_entry:
        return None

    documents: List[Document] = []
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
    return documents


def _fetch_remote_documents(case_id: str) -> List[Document]:
    client = _get_clearinghouse_client()
    documents = client.fetch_case_documents(case_id)
    _remember_documents(case_id, documents)
    try:
        _CASE_STORE.set(case_id, [doc.model_dump(mode="json") for doc in documents])
    except Exception:  # pylint: disable=broad-except
        logger.exception("Failed to persist Clearinghouse documents for case %s.", case_id)
    return documents


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


def _remember_documents(case_id: str, documents: Iterable[Document]) -> None:
    with _CASE_CACHE_LOCK:
        _CASE_CACHE[case_id] = _clone_documents(list(documents))


def _get_cached_documents(case_id: str) -> Optional[List[Document]]:
    with _CASE_CACHE_LOCK:
        cached = _CASE_CACHE.get(case_id)
    if cached is not None:
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
                    logger.warning("Unable to coerce cached document id %r to integer for case %s.", working["id"], case_id)
                    continue
            item = working
        documents.append(Document.model_validate(item))
    _remember_documents(case_id, documents)
    return _clone_documents(documents)


def _clone_documents(documents: Iterable[Document]) -> List[Document]:
    return [Document.model_validate(doc.model_dump(mode="python")) for doc in documents]


def _normalize_case_id(case_id: str) -> str:
    try:
        return str(int(case_id))
    except (TypeError, ValueError):
        return str(case_id)
