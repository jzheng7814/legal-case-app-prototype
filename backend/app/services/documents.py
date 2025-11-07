from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Iterable, List, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.db.models import DocumentSet, DocumentSetDocument, DocumentSetType, DocumentSource
from app.db.session import session_scope
from app.schemas.documents import Document, DocumentMetadata
from app.services.clearinghouse import (
    ClearinghouseClient,
    ClearinghouseError,
    ClearinghouseNotConfigured,
    ClearinghouseNotFound,
)
from app.utils.cases import normalize_case_id
from app.utils.document_signatures import compute_documents_signature

logger = logging.getLogger(__name__)

_settings = get_settings()
_DATA_ROOT = Path(__file__).resolve().parent.parent / _settings.document_root

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
    normalized = normalize_case_id(case_id)

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
    normalized = normalize_case_id(case_id)
    documents = _get_cached_documents(normalized)
    if documents is None:
        documents = list_documents(normalized)
    for document in documents:
        if document.id == document_id:
            return document
    raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found for case '{case_id}'")


def get_document_metadata(case_id: str) -> List[DocumentMetadata]:
    normalized = normalize_case_id(case_id)
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
    _persist_document_set(case_id, documents)
    return documents


def _fetch_remote_documents(case_id: str) -> List[Document]:
    client = _get_clearinghouse_client()
    documents = client.fetch_case_documents(case_id)
    _remember_documents(case_id, documents)
    _persist_document_set(case_id, documents)
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

    persisted = _load_persisted_documents(case_id)
    if not persisted:
        return None

    _remember_documents(case_id, persisted)
    return _clone_documents(persisted)


def _build_signature_payloads(documents: Iterable[Document]) -> List[Dict[str, str]]:
    payloads: List[Dict[str, str]] = []
    for doc in documents:
        payloads.append(
            {
                "id": doc.id,
                "title": doc.title or "",
                "type": doc.type or "",
                "text": doc.content or "",
            }
        )
    return payloads


def _persist_document_set(case_id: str, documents: List[Document]) -> None:
    if not documents:
        return

    payloads = _build_signature_payloads(documents)
    doc_hash = compute_documents_signature(case_id, payloads)

    try:
        with session_scope() as session:
            stmt = (
                select(DocumentSet)
                .where(
                    DocumentSet.case_identifier == case_id,
                    DocumentSet.type == DocumentSetType.CLEARINGHOUSE,
                    DocumentSet.user_id.is_(None),
                    DocumentSet.doc_hash == doc_hash,
                )
                .options(selectinload(DocumentSet.documents))
            )
            document_set = session.execute(stmt).scalars().first()
            if document_set is None:
                document_set = DocumentSet(
                    type=DocumentSetType.CLEARINGHOUSE,
                    case_identifier=case_id,
                    user_id=None,
                    doc_hash=doc_hash,
                    title=f"Case {case_id} documents",
                    description="Clearinghouse document bundle",
                )
                session.add(document_set)
            else:
                document_set.title = document_set.title or f"Case {case_id} documents"
                document_set.description = document_set.description or "Clearinghouse document bundle"
                document_set.documents.clear()
            document_set.doc_hash = doc_hash

            for position, doc in enumerate(documents):
                metadata = {
                    "id": doc.id,
                    "title": doc.title,
                    "type": doc.type,
                    "description": doc.description,
                    "source": doc.source,
                    "content": doc.content,
                }
                document_set.documents.append(
                    DocumentSetDocument(
                        source=DocumentSource.CLEARINGHOUSE,
                        remote_document_id=str(doc.id),
                        manual_document_id=None,
                        position=position,
                        display_name=doc.title,
                        doc_type=doc.type,
                        metadata_json=metadata,
                    )
                )
    except Exception:  # pylint: disable=broad-except
        logger.exception("Failed to persist document set for case %s.", case_id)


def _load_persisted_documents(case_id: str) -> Optional[List[Document]]:
    try:
        with session_scope() as session:
            stmt = (
                select(DocumentSet)
                .where(
                    DocumentSet.case_identifier == case_id,
                    DocumentSet.type == DocumentSetType.CLEARINGHOUSE,
                    DocumentSet.user_id.is_(None),
                )
                .order_by(DocumentSet.updated_at.desc())
                .options(selectinload(DocumentSet.documents))
            )
            document_set = session.execute(stmt).scalars().first()
            if document_set is None:
                return None

            documents: List[Document] = []
            for record in sorted(document_set.documents, key=lambda entry: entry.position):
                metadata = record.metadata_json or {}
                text = metadata.get("content") or metadata.get("text")
                if not text:
                    continue
                document_id = _coerce_document_id(record.remote_document_id, record.manual_document_id)
                if document_id is None:
                    continue
                documents.append(
                    Document(
                        id=document_id,
                        title=record.display_name or metadata.get("title") or f"Document {document_id}",
                        type=record.doc_type or metadata.get("type"),
                        description=metadata.get("description"),
                        source=metadata.get("source") or record.source.value,
                        content=text,
                    )
                )
            return documents or None
    except Exception:  # pylint: disable=broad-except
        logger.exception("Failed to load persisted documents for case %s.", case_id)
        return None


def _coerce_document_id(remote_document_id: Optional[str], manual_document_id: Optional[int]) -> Optional[int]:
    if remote_document_id is not None:
        try:
            return int(str(remote_document_id).strip())
        except (TypeError, ValueError):
            return None
    if manual_document_id is not None:
        return int(manual_document_id)
    return None


def _clone_documents(documents: Iterable[Document]) -> List[Document]:
    return [Document.model_validate(doc.model_dump(mode="python")) for doc in documents]
