from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import HTTPException

from app.data.checklist_store import (
    DocumentChecklistStore,
    JsonDocumentChecklistStore,
    StoredDocumentChecklist,
    StoredUserChecklistItem,
)
from app.schemas.checklists import (
    EvidenceCategory,
    EvidenceCategoryCollection,
    EvidenceCategoryValue,
    EvidenceCollection,
    EvidenceItem,
    EvidencePointer,
    LlmEvidenceCollection,
    LlmEvidencePointer,
    ChecklistItemCreateRequest,
)
from app.schemas.documents import DocumentReference
from app.services.documents import get_case_title, get_document
from app.services.llm import llm_service

logger = logging.getLogger(__name__)

_ASSET_DIR = Path(__file__).resolve().parents[1] / "resources" / "checklists"
_TEMPLATE_PATH = _ASSET_DIR / "v2" / "general_template.txt"
_ITEM_DESCRIPTIONS_PATH = _ASSET_DIR / "item_specific_info_improved.json"
_CATEGORY_METADATA_PATH = _ASSET_DIR / "v2" / "category_metadata.json"

_CHECKLIST_VERSION = "evidence-items-v1"

if not _TEMPLATE_PATH.exists():
    raise RuntimeError(f"Checklist prompt template not found at {_TEMPLATE_PATH}")

if not _ITEM_DESCRIPTIONS_PATH.exists():
    raise RuntimeError(f"Checklist item descriptions not found at {_ITEM_DESCRIPTIONS_PATH}")
if not _CATEGORY_METADATA_PATH.exists():
    raise RuntimeError(f"Checklist category metadata not found at {_CATEGORY_METADATA_PATH}")

_DOCUMENT_PROMPT_TEMPLATE = _TEMPLATE_PATH.read_text(encoding="utf-8")
_CHECKLIST_ITEM_DESCRIPTIONS: Dict[str, str] = json.loads(_ITEM_DESCRIPTIONS_PATH.read_text(encoding="utf-8"))
_CATEGORY_METADATA: List[Dict[str, object]] = json.loads(_CATEGORY_METADATA_PATH.read_text(encoding="utf-8"))

_CATEGORY_LOOKUP: Dict[str, Dict[str, object]] = {}
_CATEGORY_BY_ITEM: Dict[str, str] = {}
for category in _CATEGORY_METADATA:
    category_id = category.get("id")
    members = category.get("members") or []
    if not isinstance(category_id, str):
        raise RuntimeError("Checklist category metadata entries must include string 'id' keys.")
    if category_id in _CATEGORY_LOOKUP:
        raise RuntimeError(f"Duplicate checklist category id detected: {category_id}")
    _CATEGORY_LOOKUP[category_id] = {
        "id": category_id,
        "label": category.get("label") or category_id,
        "color": category.get("color") or "#000000",
        "members": list(members),
    }
    for member in members:
        if member in _CATEGORY_BY_ITEM:
            raise RuntimeError(f"Checklist item '{member}' assigned to multiple categories.")
        _CATEGORY_BY_ITEM[member] = category_id

_CATEGORY_ORDER = [category["id"] for category in _CATEGORY_METADATA if isinstance(category.get("id"), str)]

_DOCUMENT_CACHE: Dict[str, EvidenceCollection] = {}
_DOCUMENT_CACHE_LOCK = asyncio.Lock()
_IN_FLIGHT_EXTRACTIONS: Dict[str, asyncio.Task[EvidenceCollection]] = {}
_IN_FLIGHT_LOCK = asyncio.Lock()

_CHECKLIST_DB_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "flat_db" / "document_checklist_items_v2.json"
)
_DOCUMENT_CHECKLIST_STORE: DocumentChecklistStore = JsonDocumentChecklistStore(_CHECKLIST_DB_PATH)

_MAX_DOCUMENT_CHARS = 12_000


def get_checklist_definitions() -> Dict[str, str]:
    """Return a copy of the checklist item descriptions."""
    return dict(_CHECKLIST_ITEM_DESCRIPTIONS)


def get_category_metadata(include_members: bool = False) -> List[Dict[str, object]]:
    """Return checklist category metadata for UI consumption."""
    metadata: List[Dict[str, object]] = []
    for category_id in _CATEGORY_ORDER:
        category = _CATEGORY_LOOKUP[category_id]
        if include_members:
            metadata.append(
                {
                    "id": category["id"],
                    "label": category["label"],
                    "color": category["color"],
                    "members": list(category.get("members", [])),
                }
            )
        else:
            metadata.append(
                {
                    "id": category["id"],
                    "label": category["label"],
                    "color": category["color"],
                }
            )
    return metadata


def _truncate_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n[truncated for prompt length]"


def _truncate_for_prompt(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit], True


@dataclass(frozen=True)
class TokenizedSentence:
    sentence_id: int
    text: str
    start: int
    end: int


@dataclass(frozen=True)
class TokenizedDocument:
    document_id: int
    title: str
    type: str
    text: str
    truncated: bool
    sentences: List[TokenizedSentence]


_SENTENCE_SPLIT_PATTERN = re.compile(r".+?(?:[.!?](?=\s|$)|\n{2,}|$)", flags=re.DOTALL)


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


def _document_sort_key(doc_ref: DocumentReference) -> tuple:
    ecf_flags = _parse_ecf_key(doc_ref.ecf_number)
    return (
        0 if doc_ref.is_docket else 1,
        ecf_flags[0],
        ecf_flags[1],
        ecf_flags[2],
        doc_ref.id,
    )


def _resolve_document_payloads(case_id: str, documents: List[DocumentReference]) -> List[Dict[str, str]]:
    payloads: List[Dict[str, str]] = []
    for doc_ref in documents:
        if doc_ref.include_full_text:
            if not doc_ref.content:
                raise HTTPException(status_code=400, detail=f"Document '{doc_ref.id}' missing inline content.")
            text = doc_ref.content
            title = doc_ref.title or doc_ref.alias or doc_ref.id
            doc_type = None
        else:
            document = get_document(case_id, doc_ref.id)
            text = doc_ref.content or document.content
            title = doc_ref.title or doc_ref.alias or document.title or document.id
            doc_type = document.type

        payloads.append(
            {
                "id": int(doc_ref.id),
                "title": title,
                "type": doc_type or "",
                "text": text or "",
            }
        )
    return payloads


def _build_text_lookup_from_references(case_id: str, documents: List[DocumentReference]) -> Dict[int, str]:
    payloads = _resolve_document_payloads(case_id, documents)
    return {int(payload["id"]): payload.get("text", "") for payload in payloads}


def _tokenize_document(payload: Dict[str, str]) -> TokenizedDocument:
    truncated_text, truncated = _truncate_for_prompt(payload["text"], _MAX_DOCUMENT_CHARS)
    sentences: List[TokenizedSentence] = []
    for match in _SENTENCE_SPLIT_PATTERN.finditer(truncated_text):
        start, end = match.span()
        segment = truncated_text[start:end]
        stripped = segment.strip()
        if not stripped:
            continue
        leading_ws = len(segment) - len(segment.lstrip())
        normalized_start = start + leading_ws
        normalized_end = normalized_start + len(stripped)
        sentences.append(
            TokenizedSentence(
                sentence_id=len(sentences) + 1,
                text=stripped,
                start=normalized_start,
                end=normalized_end,
            )
        )
    if not sentences and truncated_text:
        stripped = truncated_text.strip()
        sentences.append(
            TokenizedSentence(
                sentence_id=1,
                text=stripped,
                start=truncated_text.find(stripped),
                end=truncated_text.find(stripped) + len(stripped),
            )
        )
    return TokenizedDocument(
        document_id=payload["id"],
        title=payload.get("title") or "",
        type=payload.get("type") or "",
        text=truncated_text,
        truncated=truncated,
        sentences=sentences,
    )


def _build_case_documents_block(documents: List[TokenizedDocument]) -> str:
    blocks: List[str] = []
    for doc in documents:
        header = f"Document {doc.document_id}"
        if doc.title:
            header += f" — {doc.title}"
        if doc.type:
            header += f" ({doc.type})"

        lines: List[str] = [header]
        for sentence in doc.sentences:
            lines.append(f"Sentence {sentence.sentence_id}: {sentence.text}")
        if doc.truncated:
            lines.append(f"[text truncated after {_MAX_DOCUMENT_CHARS} characters]")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _build_document_catalog(documents: List[TokenizedDocument]) -> str:
    lines: List[str] = []
    for doc in documents:
        descriptor_parts: List[str] = []
        if doc.title:
            descriptor_parts.append(doc.title)
        if doc.type:
            descriptor_parts.append(f"({doc.type})")
        descriptor = " ".join(part for part in descriptor_parts if part).strip()
        if not descriptor:
            descriptor = f"Document {doc.document_id}"
        lines.append(f"- Document {doc.document_id}: {descriptor}")
    return "\n".join(lines) if lines else "No documents were supplied."


def _compute_documents_signature(case_id: str, documents: List[TokenizedDocument], case_name: str) -> str:
    digest = hashlib.sha256()
    digest.update(case_id.encode("utf-8"))
    digest.update(_CHECKLIST_VERSION.encode("utf-8"))
    digest.update(case_name.encode("utf-8"))
    for doc in documents:
        digest.update(str(doc.document_id).encode("utf-8"))
        digest.update(doc.title.encode("utf-8"))
        digest.update(doc.type.encode("utf-8"))
        digest.update(doc.text.encode("utf-8"))
    return digest.hexdigest()


def _clean_case_name(raw_value: Optional[str]) -> Optional[str]:
    if not isinstance(raw_value, str):
        return None
    cleaned = " ".join(raw_value.split()).strip()
    return cleaned or None


def _resolve_case_name(case_id: str, documents: List[DocumentReference]) -> str:
    cached = _clean_case_name(get_case_title(case_id))
    if cached:
        return cached

    for ref in documents:
        fallback = _clean_case_name(ref.title) or _clean_case_name(ref.alias)
        if fallback:
            return fallback

    raise HTTPException(status_code=500, detail="Case title unavailable for checklist extraction.")


def _copy_collection(collection: EvidenceCollection) -> EvidenceCollection:
    return collection.model_copy(deep=True)


async def _resolve_cached_collection(
    case_id: str, documents: List[DocumentReference], case_name: str
) -> tuple[EvidenceCollection | None, List[TokenizedDocument], str]:
    sorted_docs = sorted(documents, key=_document_sort_key)
    payloads = _resolve_document_payloads(case_id, sorted_docs)
    tokenized = [_tokenize_document(payload) for payload in payloads]
    signature = _compute_documents_signature(case_id, tokenized, case_name)
    text_lookup = {doc.document_id: doc.text for doc in tokenized}

    async with _DOCUMENT_CACHE_LOCK:
        cached = _DOCUMENT_CACHE.get(signature)
    if cached is not None:
        return _copy_collection(cached), tokenized, signature

    stored = _DOCUMENT_CHECKLIST_STORE.get(case_id, signature=signature)
    if stored is not None:
        sanitized = _strip_sentence_ids_from_collection(stored.items, text_lookup)
        if sanitized != stored.items:
            _DOCUMENT_CHECKLIST_STORE.set(
                case_id,
                signature=stored.signature,
                items=sanitized,
                user_items=stored.user_items,
            )
        cached_copy = _copy_collection(sanitized)
        async with _DOCUMENT_CACHE_LOCK:
            _DOCUMENT_CACHE[signature] = cached_copy
        return _copy_collection(cached_copy), tokenized, signature

    return None, tokenized, signature


async def get_document_checklists_if_cached(
    case_id: str, documents: List[DocumentReference]
) -> EvidenceCollection | None:
    case_name = _resolve_case_name(case_id, documents)
    cached, tokenized, _ = await _resolve_cached_collection(case_id, documents, case_name)
    if cached is None:
        return None
    text_lookup = {doc.document_id: doc.text for doc in tokenized}
    sanitized = _strip_sentence_ids_from_collection(cached, text_lookup)
    return sanitized


async def ensure_document_checklist_record(
    case_id: str, documents: List[DocumentReference]
) -> StoredDocumentChecklist:
    """Ensure checklist extraction results exist for a case and return the stored payload."""
    sorted_docs = sorted(documents, key=_document_sort_key)
    text_lookup = _build_text_lookup_from_references(case_id, sorted_docs)
    stored = _DOCUMENT_CHECKLIST_STORE.get(case_id)
    if stored is not None:
        sanitized_items = _strip_sentence_ids_from_collection(stored.items, text_lookup)
        if sanitized_items != stored.items:
            _DOCUMENT_CHECKLIST_STORE.set(
                case_id,
                signature=stored.signature,
                items=sanitized_items,
                user_items=stored.user_items,
            )
        return StoredDocumentChecklist(
            signature=stored.signature,
            items=sanitized_items,
            user_items=stored.user_items,
            version=stored.version,
        )

    await extract_document_checklists(case_id, sorted_docs)
    stored = _DOCUMENT_CHECKLIST_STORE.get(case_id)
    if stored is None:
        raise RuntimeError(f"Checklist extraction for case {case_id} failed to persist.")
    return stored


def _build_checklist_bins_block() -> str:
    lines: List[str] = []
    for category_id in _CATEGORY_ORDER:
        meta = _CATEGORY_LOOKUP[category_id]
        label = meta["label"]
        lines.append(f"- Evidence bin {category_id} — {label}")
        members = meta.get("members") or []
        if members:
            lines.append("  Guidance:")
            for member in members:
                desc = (_CHECKLIST_ITEM_DESCRIPTIONS.get(member) or "").strip()
                guidance = desc or "no description provided"
                lines.append(f"  - {member}: {guidance}")
        else:
            lines.append("  Guidance: none listed.")
    return "\n".join(lines)


def _build_sentence_index(documents: List[TokenizedDocument]) -> Dict[int, Dict[int, TokenizedSentence]]:
    index: Dict[int, Dict[int, TokenizedSentence]] = {}
    for doc in documents:
        sentence_map = {sentence.sentence_id: sentence for sentence in doc.sentences}
        index[doc.document_id] = sentence_map
    return index


def _resolve_sentence_evidence(
    evidence: LlmEvidencePointer,
    sentence_index: Dict[int, Dict[int, TokenizedSentence]],
    text_lookup: Optional[Dict[int, str]] = None,
) -> EvidencePointer:
    sentence_ids = evidence.sentence_ids or []
    sentence_ids = list(dict.fromkeys(sentence_ids))  # de-duplicate while preserving order
    sentences_for_doc = sentence_index.get(evidence.document_id) or {}
    matched = [sentences_for_doc[sid] for sid in sentence_ids if sid in sentences_for_doc]
    if not matched:
        logger.warning(
            "No matching sentences for evidence (document_id=%s, sentence_ids=%s)",
            evidence.document_id,
            sentence_ids,
        )
        return EvidencePointer(
            document_id=evidence.document_id,
            start_offset=None,
            end_offset=None,
            text=None,
            verified=False,
        )

    start = min(sentence.start for sentence in matched)
    end = max(sentence.end for sentence in matched)
    doc_text = (text_lookup or {}).get(evidence.document_id)
    span_text = None
    if doc_text is not None and 0 <= start < end <= len(doc_text):
        span_text = doc_text[start:end]

    return EvidencePointer(
        document_id=evidence.document_id,
        start_offset=start,
        end_offset=end,
        text=span_text,
        verified=True,
    )
def _resolve_evidence_items(
    collection: LlmEvidenceCollection,
    sentence_index: Dict[int, Dict[int, TokenizedSentence]],
    text_lookup: Optional[Dict[int, str]] = None,
) -> EvidenceCollection:
    resolved_items: List[EvidenceItem] = []
    for item in collection.items:
        resolved_pointer = _resolve_sentence_evidence(item.evidence, sentence_index, text_lookup)
        resolved_items.append(
            EvidenceItem(
                bin_id=item.bin_id,
                value=item.value,
                evidence=resolved_pointer,
            )
        )
    return EvidenceCollection(items=resolved_items)


def _strip_sentence_ids_from_collection(
    collection: EvidenceCollection, text_lookup: Optional[Dict[int, str]] = None
) -> EvidenceCollection:
    """Return a copy with evidence text populated when possible."""
    cleaned_items: List[EvidenceItem] = []
    for item in collection.items:
        ev = item.evidence
        doc_text = (text_lookup or {}).get(ev.document_id)
        start = ev.start_offset
        end = ev.end_offset
        text = ev.text
        if doc_text is not None and start is not None and end is not None and 0 <= start < end <= len(doc_text):
            text = doc_text[start:end]
        cleaned_items.append(
            EvidenceItem(
                bin_id=item.bin_id,
                value=item.value,
                evidence=EvidencePointer(
                    document_id=ev.document_id,
                    start_offset=start,
                    end_offset=end,
                    text=text,
                    verified=ev.verified,
                ),
            )
        )
    return EvidenceCollection(items=cleaned_items)


def build_category_collection(record: StoredDocumentChecklist) -> EvidenceCategoryCollection:
    """Map extracted evidence items into UI categories."""
    sanitized_items = _strip_sentence_ids_from_collection(record.items)
    categories: Dict[str, EvidenceCategory] = {
        meta_id: EvidenceCategory(
            id=meta_id,
            label=_CATEGORY_LOOKUP[meta_id]["label"],
            color=_CATEGORY_LOOKUP[meta_id]["color"],
            values=[],
        )
        for meta_id in _CATEGORY_ORDER
    }

    bin_counters: Dict[str, int] = {meta_id: 0 for meta_id in _CATEGORY_ORDER}
    ai_order: Dict[str, int] = {}
    user_order: Dict[str, int] = {
        _build_user_value_id(entry.id): idx for idx, entry in enumerate(record.user_items)
    }

    for index, item in enumerate(sanitized_items.items):
        category = categories.get(item.bin_id)
        if not category:
            continue
        value_index = bin_counters[item.bin_id]
        bin_counters[item.bin_id] += 1
        ev = item.evidence
        value_id = _build_ai_value_id(item.bin_id, value_index)
        ai_order[value_id] = index
        category.values.append(
            EvidenceCategoryValue(
                id=value_id,
                value=item.value,
                text=item.value,
                document_id=ev.document_id,
                start_offset=ev.start_offset,
                end_offset=ev.end_offset,
            )
        )

    for entry in record.user_items:
        category = categories.get(entry.category_id)
        if not category:
            continue
        category.values.append(
            EvidenceCategoryValue(
                id=_build_user_value_id(entry.id),
                value=entry.value,
                text=entry.value,
                document_id=entry.document_id,
                start_offset=entry.start_offset,
                end_offset=entry.end_offset,
            )
        )

    for category in categories.values():
        category.values.sort(
            key=lambda value: (
                0 if value.id in ai_order else 1,
                ai_order.get(value.id, len(ai_order) + user_order.get(value.id, len(user_order))),
                value.document_id is None,
                value.document_id or 0,
                value.start_offset if value.start_offset is not None else 0,
                value.id,
            )
        )

    ordered = [categories[category_id] for category_id in _CATEGORY_ORDER]
    sanitized_record = StoredDocumentChecklist(
        signature=record.signature,
        items=sanitized_items,
        user_items=record.user_items,
        version=record.version,
    )
    combined_signature = _build_combined_signature(sanitized_record)
    return EvidenceCategoryCollection(signature=combined_signature, categories=ordered)


def _build_ai_value_id(bin_id: str, value_index: int) -> str:
    return f"ai::{bin_id}::{value_index}"


def _build_user_value_id(user_item_id: str) -> str:
    return f"user::{user_item_id}"


def _parse_value_identifier(value_id: str) -> Optional[Dict[str, object]]:
    parts = value_id.split("::")
    if not parts:
        return None
    prefix = parts[0]
    if prefix == "ai" and len(parts) == 3:
        try:
            index = int(parts[2])
        except (TypeError, ValueError):
            return None
        return {"source": "ai", "bin_id": parts[1], "value_index": index}
    if prefix == "user" and len(parts) == 2:
        return {"source": "user", "user_id": parts[1]}
    return None


def _remove_ai_value_from_collection(
    collection: EvidenceCollection, bin_id: str, value_index: int
) -> Optional[EvidenceCollection]:
    updated_items: List[EvidenceItem] = []
    removed = False
    counter = 0
    for item in collection.items:
        if item.bin_id == bin_id:
            if counter == value_index:
                removed = True
                counter += 1
                continue
            counter += 1
        updated_items.append(item)
    if not removed:
        return None
    return EvidenceCollection(items=updated_items)


async def _refresh_cache(signature: str, collection: EvidenceCollection) -> None:
    async with _DOCUMENT_CACHE_LOCK:
        _DOCUMENT_CACHE[signature] = _copy_collection(collection)


def append_user_checklist_value(
    case_id: str,
    record: StoredDocumentChecklist,
    payload: ChecklistItemCreateRequest,
) -> StoredDocumentChecklist:
    category_id = payload.category_id
    if category_id not in _CATEGORY_LOOKUP:
        raise HTTPException(status_code=400, detail=f"Unknown checklist category '{category_id}'.")
    if (
        payload.start_offset is not None
        and payload.end_offset is not None
        and payload.start_offset >= payload.end_offset
    ):
        raise HTTPException(status_code=400, detail="Checklist highlights must have a positive length.")

    trimmed_value = payload.text.strip()
    if not trimmed_value:
        raise HTTPException(status_code=400, detail="Checklist text is required.")

    entry = StoredUserChecklistItem(
        id=str(uuid.uuid4()),
        category_id=category_id,
        value=trimmed_value,
        document_id=payload.document_id,
        start_offset=payload.start_offset,
        end_offset=payload.end_offset,
    )
    next_entries = [*record.user_items, entry]
    sanitized_items = _strip_sentence_ids_from_collection(record.items)
    _DOCUMENT_CHECKLIST_STORE.set(
        case_id,
        signature=record.signature,
        items=sanitized_items,
        user_items=next_entries,
    )
    return StoredDocumentChecklist(signature=record.signature, items=sanitized_items, user_items=next_entries)


async def remove_checklist_value(case_id: str, value_id: str) -> StoredDocumentChecklist:
    record = _DOCUMENT_CHECKLIST_STORE.get(case_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Checklist not found for this case.")
    parsed = _parse_value_identifier(value_id)
    if parsed is None:
        raise HTTPException(status_code=404, detail="Checklist item not found.")
    if parsed["source"] == "user":
        user_id = parsed["user_id"]
        next_entries = [entry for entry in record.user_items if entry.id != user_id]
        if len(next_entries) == len(record.user_items):
            raise HTTPException(status_code=404, detail="Checklist item not found.")
        _DOCUMENT_CHECKLIST_STORE.set(
            case_id,
            signature=record.signature,
            items=record.items,
            user_items=next_entries,
        )
        return StoredDocumentChecklist(signature=record.signature, items=record.items, user_items=next_entries)

    bin_id = parsed["bin_id"]
    value_index = parsed["value_index"]
    updated_collection = _remove_ai_value_from_collection(record.items, bin_id, value_index)
    if updated_collection is None:
        raise HTTPException(status_code=404, detail="Checklist item not found.")
    sanitized_items = _strip_sentence_ids_from_collection(updated_collection)
    _DOCUMENT_CHECKLIST_STORE.set(
        case_id,
        signature=record.signature,
        items=sanitized_items,
        user_items=record.user_items,
    )
    await _refresh_cache(record.signature, sanitized_items)
    return StoredDocumentChecklist(signature=record.signature, items=sanitized_items, user_items=record.user_items)


def _build_combined_signature(record: StoredDocumentChecklist) -> str:
    if not record.user_items:
        return record.signature
    digest = hashlib.sha256(record.signature.encode("utf-8"))
    for entry in sorted(record.user_items, key=lambda item: item.id):
        digest.update(entry.id.encode("utf-8"))
        digest.update(entry.category_id.encode("utf-8"))
        digest.update(entry.value.encode("utf-8"))
        digest.update(str(entry.document_id or "").encode("utf-8"))
        digest.update(str(entry.start_offset or "").encode("utf-8"))
        digest.update(str(entry.end_offset or "").encode("utf-8"))
    return f"{record.signature}:{digest.hexdigest()}"


async def extract_document_checklists(case_id: str, documents: List[DocumentReference]) -> EvidenceCollection:
    if not documents:
        return EvidenceCollection(items=[])

    case_name = _resolve_case_name(case_id, documents)
    cached, tokenized_docs, signature = await _resolve_cached_collection(case_id, documents, case_name)
    if cached is not None:
        logger.debug("Checklist extraction cache hit for signature %s", signature)
        return cached

    async with _IN_FLIGHT_LOCK:
        task = _IN_FLIGHT_EXTRACTIONS.get(signature)
        if task is None or task.done():
            task = asyncio.create_task(_run_extraction(case_id, tokenized_docs, signature, case_name))
            _IN_FLIGHT_EXTRACTIONS[signature] = task

    try:
        result = await task
    finally:
        if task.done():
            async with _IN_FLIGHT_LOCK:
                current = _IN_FLIGHT_EXTRACTIONS.get(signature)
                if current is task:
                    _IN_FLIGHT_EXTRACTIONS.pop(signature, None)

    return _copy_collection(result)


async def _run_extraction(
    case_id: str, tokenized_docs: List[TokenizedDocument], signature: str, case_name: str
) -> EvidenceCollection:
    # Use the Agentic Worker for extraction
    from app.services.agent.driver import run_extraction_agent

    try:
        # Run the agent
        # Note: The agent will access documents via the documents service using case_id
        # We don't pass tokenized_docs explicitly as the agent handles its own reading strategy
        result = await run_extraction_agent(case_id)
        
        # Persist results
        _DOCUMENT_CHECKLIST_STORE.set(case_id, signature=signature, items=result)
        
        # Update cache
        async with _DOCUMENT_CACHE_LOCK:
            _DOCUMENT_CACHE[signature] = _copy_collection(result)
            
        return _copy_collection(result)
        
    except Exception:
        logger.exception("Agent extraction failed for case %s", case_id)
        raise
