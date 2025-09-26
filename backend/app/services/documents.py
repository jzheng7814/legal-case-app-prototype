from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List

from fastapi import HTTPException

from app.core.config import get_settings
from app.schemas.documents import Document, DocumentMetadata

_settings = get_settings()
_DATA_ROOT = Path(__file__).resolve().parent.parent / _settings.document_root


@lru_cache
def _load_catalog() -> Dict[str, Any]:
    catalog_path = _DATA_ROOT / "catalog.json"
    if not catalog_path.exists():
        raise RuntimeError(f"Document catalog not found at {catalog_path}")
    with catalog_path.open("r", encoding="utf-8") as infile:
        return json.load(infile)


def list_documents(case_id: str) -> List[Document]:
    catalog = _load_catalog()
    case_entry = catalog.get("cases", {}).get(case_id)
    if not case_entry:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")

    documents: List[Document] = []
    for item in case_entry["documents"]:
        content = _load_document_text(item["filename"])
        documents.append(
            Document(
                id=item["id"],
                name=item["name"],
                type=item["type"],
                description=item.get("description"),
                source="demo",
                content=content,
            )
        )
    return documents


def get_document(case_id: str, document_id: str) -> Document:
    for document in list_documents(case_id):
        if document.id == document_id:
            return document
    raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found for case '{case_id}'")


def _load_document_text(filename: str) -> str:
    doc_path = _DATA_ROOT / filename
    if not doc_path.exists():
        raise HTTPException(status_code=404, detail=f"Document file '{filename}' missing on server")
    with doc_path.open("r", encoding="utf-8") as infile:
        return infile.read()


def get_document_metadata(case_id: str) -> List[DocumentMetadata]:
    # Utility for returning metadata without content.
    docs = list_documents(case_id)
    return [
        DocumentMetadata(
            id=doc.id,
            name=doc.name,
            type=doc.type,
            description=doc.description,
            source=doc.source,
        )
        for doc in docs
    ]
