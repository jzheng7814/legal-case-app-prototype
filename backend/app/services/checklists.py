from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from difflib import SequenceMatcher
import re
from pathlib import Path
from typing import Dict, List

from fastapi import HTTPException

from rapidfuzz import fuzz, process

from app.data.checklist_store import DocumentChecklistStore, JsonDocumentChecklistStore
from app.schemas.checklists import (
    ChecklistCollection,
    ChecklistEvidence,
    ChecklistExtractionPayload,
    ChecklistItemResult,
    SummaryChecklistExtractionPayload,
)
from app.schemas.documents import DocumentReference
from app.services.documents import get_document
from app.services.llm import llm_service

logger = logging.getLogger(__name__)

_ASSET_DIR = Path(__file__).resolve().parents[1] / "resources" / "checklists"
_TEMPLATE_PATH = _ASSET_DIR / "general_template.txt"
_ITEM_DESCRIPTIONS_PATH = _ASSET_DIR / "item_specific_info_improved.json"

if not _TEMPLATE_PATH.exists():
    raise RuntimeError(f"Checklist prompt template not found at {_TEMPLATE_PATH}")

if not _ITEM_DESCRIPTIONS_PATH.exists():
    raise RuntimeError(f"Checklist item descriptions not found at {_ITEM_DESCRIPTIONS_PATH}")

_DOCUMENT_PROMPT_TEMPLATE = _TEMPLATE_PATH.read_text(encoding="utf-8")
_CHECKLIST_ITEM_DESCRIPTIONS: Dict[str, str] = json.loads(_ITEM_DESCRIPTIONS_PATH.read_text(encoding="utf-8"))

_DOCUMENT_CACHE: Dict[str, ChecklistCollection] = {}
_DOCUMENT_CACHE_LOCK = asyncio.Lock()

_CHECKLIST_DB_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "flat_db" / "document_checklist_items.json"
)
_DOCUMENT_CHECKLIST_STORE: DocumentChecklistStore = JsonDocumentChecklistStore(_CHECKLIST_DB_PATH)

_MAX_DOCUMENT_CHARS = 12_000
_MAX_SUMMARY_CHARS = 6_000
SUMMARY_DOCUMENT_ID = -1


def get_checklist_definitions() -> Dict[str, str]:
    """Return a copy of the checklist item descriptions."""
    return dict(_CHECKLIST_ITEM_DESCRIPTIONS)


def _truncate_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n[truncated for prompt length]"


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


def _build_case_documents_block(payloads: List[Dict[str, str]]) -> str:
    blocks: List[str] = []
    for payload in payloads:
        truncated = _truncate_text(payload["text"], _MAX_DOCUMENT_CHARS)
        doc_id = payload["id"]
        doc_header = f"Document {doc_id}"
        if payload.get("title"):
            doc_header += f" — {payload['title']}"
        if payload.get("type"):
            doc_header += f" ({payload['type']})"
        blocks.append(f"{doc_header}\n{truncated}")
    return "\n\n".join(blocks)


def _build_document_catalog(payloads: List[Dict[str, str]]) -> str:
    lines: List[str] = []
    for payload in sorted(payloads, key=lambda item: item["id"]):
        descriptor_parts: List[str] = []
        if payload.get("title"):
            descriptor_parts.append(payload["title"])
        if payload.get("type"):
            descriptor_parts.append(f"({payload['type']})")
        descriptor = " ".join(part for part in descriptor_parts if part).strip()
        if not descriptor:
            descriptor = f"Document {payload['id']}"
        lines.append(f"- Document {payload['id']}: {descriptor}")
    return "\n".join(lines) if lines else "No documents were supplied."


def _compute_documents_signature(case_id: str, payloads: List[Dict[str, str]]) -> str:
    digest = hashlib.sha256(case_id.encode("utf-8"))
    for payload in sorted(payloads, key=lambda item: item["id"]):
        digest.update(str(payload["id"]).encode("utf-8"))
        digest.update(payload["title"].encode("utf-8"))
        digest.update(payload["type"].encode("utf-8"))
        digest.update(payload["text"].encode("utf-8"))
    return digest.hexdigest()


def _copy_collection(collection: ChecklistCollection) -> ChecklistCollection:
    return collection.model_copy(deep=True)


async def _resolve_cached_collection(
    case_id: str, documents: List[DocumentReference]
) -> tuple[ChecklistCollection | None, List[Dict[str, str]], str]:
    payloads = _resolve_document_payloads(case_id, documents)
    signature = _compute_documents_signature(case_id, payloads)

    async with _DOCUMENT_CACHE_LOCK:
        cached = _DOCUMENT_CACHE.get(signature)
    if cached is not None:
        return _copy_collection(cached), payloads, signature

    stored = _DOCUMENT_CHECKLIST_STORE.get(case_id, signature=signature)
    if stored is not None:
        cached_copy = _copy_collection(stored.items)
        async with _DOCUMENT_CACHE_LOCK:
            _DOCUMENT_CACHE[signature] = cached_copy
        return _copy_collection(cached_copy), payloads, signature

    return None, payloads, signature


async def get_document_checklists_if_cached(
    case_id: str, documents: List[DocumentReference]
) -> ChecklistCollection | None:
    cached, _, _ = await _resolve_cached_collection(case_id, documents)
    return cached


def _validate_evidence_offsets(
    item_name: str,
    extraction: ChecklistExtractionPayload,
    text_lookup: Dict[int, str],
) -> None:
    whitespace_collapse = re.compile(r"\s+")

    def _find_exact_matches(haystack: str, needle: str) -> List[int]:
        matches: List[int] = []
        start = 0
        while True:
            index = haystack.find(needle, start)
            if index == -1:
                break
            matches.append(index)
            start = index + 1
        if matches:
            return matches

        haystack_lower = haystack.lower()
        needle_lower = needle.lower()
        if haystack_lower == haystack and needle_lower == needle:
            return matches

        start = 0
        while True:
            index = haystack_lower.find(needle_lower, start)
            if index == -1:
                break
            matches.append(index)
            start = index + 1
        return matches

    def _locate_regex_match(haystack: str, needle: str) -> tuple[int, int] | None:
        stripped = needle.strip()
        if not stripped:
            return None
        escaped = re.escape(stripped)
        pattern = whitespace_collapse.sub(r"\\s+", escaped)
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error:
            return None
        match = regex.search(haystack)
        if not match:
            return None
        return match.start(), match.end()

    def _build_normalized_indices(text: str) -> tuple[str, List[int]]:
        normalized_chars: List[str] = []
        mapping: List[int] = []
        i = 0
        length = len(text)
        while i < length:
            ch = text[i]
            if ch == "-" and i + 1 < length and text[i + 1] == "\n":
                i += 2
                continue
            if ch == "\r":
                i += 1
                continue
            if ch.isspace():
                j = i + 1
                while j < length:
                    nxt = text[j]
                    if nxt == "-" and j + 1 < length and text[j + 1] == "\n":
                        j += 2
                        continue
                    if not nxt.isspace():
                        break
                    j += 1
                normalized_chars.append(" ")
                mapping.append(i)
                i = j
                continue
            normalized_chars.append(ch)
            mapping.append(i)
            i += 1
        return "".join(normalized_chars), mapping

    def _locate_fuzzy(
        haystack: str,
        needle: str,
        target: int,
        document_id: int,
    ) -> tuple[int, str, str] | None:
        trimmed = needle.strip()
        if not trimmed:
            return None

        haystack_len = len(haystack)
        if haystack_len == 0:
            return None

        radius = max(len(trimmed) * 4, 1_500)
        window_size = max(len(trimmed) + 120, 400)
        start_bound = max(0, target - radius)
        end_bound = min(haystack_len, target + radius)
        if start_bound >= end_bound:
            start_bound = max(0, min(target, haystack_len))
            end_bound = min(haystack_len, start_bound + window_size)

        windows: List[str] = []
        offsets: List[int] = []
        step = max(50, window_size // 2)
        index = start_bound
        while index < end_bound:
            segment = haystack[index : min(haystack_len, index + window_size)]
            if segment:
                windows.append(segment)
                offsets.append(index)
            index += step

        if not windows:
            windows = [haystack]
            offsets = [0]

        result = process.extractOne(
            needle,
            windows,
            scorer=fuzz.partial_ratio,
            score_cutoff=78,
        )
        if not result:
            lowered = needle.lower()
            for idx, candidate in enumerate(windows):
                if lowered in candidate.lower():
                    result = (candidate, 80, idx)  # type: ignore[assignment]
                    break
            if not result:
                return None

        _, score, win_index = result
        segment = windows[win_index]
        base_offset = offsets[win_index]

        lowered_segment = segment.lower()
        lowered_needle = needle.lower()
        relative = lowered_segment.find(lowered_needle)
        span_length = len(needle)

        if relative == -1:
            matcher = SequenceMatcher(None, lowered_needle, lowered_segment)
            match = matcher.find_longest_match(0, len(lowered_needle), 0, len(lowered_segment))
            if match.size == 0:
                return None
            relative = match.b
            span_length = max(match.size, len(trimmed))

        absolute_start = base_offset + relative
        absolute_end = min(haystack_len, absolute_start + span_length)
        if absolute_start < 0 or absolute_start >= absolute_end:
            return None

        snippet = haystack[absolute_start:absolute_end]
        if not snippet.strip():
            return None

        final_score = fuzz.partial_ratio(needle, snippet)
        if final_score < 65:
            return None

        logger.debug(
            "Fuzzy matched checklist evidence (item=%s, document_id=%s, score=%s, start=%s)",
            item_name,
            document_id,
            final_score,
            absolute_start,
        )
        return absolute_start, snippet, f"fuzzy_score={final_score}"

    filtered_values = []
    for extracted_item in extraction.extracted:
        discard_value = False
        validated_evidence: List[ChecklistEvidence] = []
        for evidence in extracted_item.evidence:
            doc_text = text_lookup.get(evidence.document_id)
            if doc_text is None:
                logger.warning(
                    "Discarding checklist value due to missing document (item=%s, document_id=%s)",
                    item_name,
                    evidence.document_id,
                )
                discard_value = True
                break

            evidence.verified = False

            target_offset = evidence.start_offset if evidence.start_offset is not None else 0
            matches = _find_exact_matches(doc_text, evidence.text)
            replacement_text = evidence.text
            chosen_start: int | None = None
            chosen_end: int | None = None

            if matches:
                if len(matches) == 1:
                    chosen_start = matches[0]
                else:
                    chosen_start = min(
                        matches,
                        key=lambda pos: (
                            abs(pos - target_offset),
                            pos,
                        ),
                    )
                chosen_end = chosen_start + len(replacement_text)
            else:
                regex_match = _locate_regex_match(doc_text, evidence.text)
                if regex_match is not None:
                    chosen_start, chosen_end = regex_match
                    replacement_text = doc_text[chosen_start:chosen_end]
                    logger.debug(
                        "Regex matched checklist evidence (item=%s, document_id=%s, start=%s)",
                        item_name,
                        evidence.document_id,
                        chosen_start,
                    )
                else:
                    normalized_text, index_map = _build_normalized_indices(doc_text)
                    normalized_needle = whitespace_collapse.sub(" ", evidence.text.strip())
                    normalized_pos = normalized_text.find(normalized_needle)
                    if normalized_pos == -1:
                        normalized_pos = normalized_text.lower().find(normalized_needle.lower())
                    if normalized_pos != -1 and index_map:
                        start_index = index_map[min(normalized_pos, len(index_map) - 1)]
                        end_index = min(normalized_pos + len(normalized_needle) - 1, len(index_map) - 1)
                        chosen_start = start_index
                        chosen_end = index_map[end_index] + 1
                        replacement_text = doc_text[chosen_start:chosen_end]
                        logger.debug(
                            "Whitespace-normalized match for checklist evidence (item=%s, document_id=%s, start=%s)",
                            item_name,
                            evidence.document_id,
                            chosen_start,
                        )
                    else:
                        fuzzy_match = _locate_fuzzy(
                            doc_text,
                            evidence.text,
                            target_offset,
                            evidence.document_id,
                        )
                        if fuzzy_match is None:
                            logger.warning(
                                "Unable to verify checklist evidence (item=%s, document_id=%s, provided_start=%s, text=%r)",
                                item_name,
                                evidence.document_id,
                                evidence.start_offset,
                                evidence.text[:120],
                            )
                        else:
                            chosen_start, replacement_text, diagnostics = fuzzy_match
                            chosen_end = chosen_start + len(replacement_text)
                            logger.debug(
                                "Fuzzy fallback accepted for checklist evidence (item=%s, document_id=%s, start=%s, diagnostics=%s)",
                                item_name,
                                evidence.document_id,
                                chosen_start,
                                diagnostics,
                            )

            if chosen_start is None or chosen_end is None:
                evidence.start_offset = None
                validated_evidence.append(evidence)
                continue

            if replacement_text != evidence.text:
                logger.debug(
                    "Adjusted checklist evidence text to align with document (item=%s, document_id=%s)",
                    item_name,
                    evidence.document_id,
                )
                evidence.text = replacement_text

            if evidence.start_offset != chosen_start:
                logger.debug(
                    "Adjusted checklist evidence start offset (item=%s, document_id=%s, old_start=%s, new_start=%s)",
                    item_name,
                    evidence.document_id,
                    evidence.start_offset,
                    chosen_start,
                )
                evidence.start_offset = chosen_start

            evidence.verified = True
            validated_evidence.append(evidence)

        if discard_value:
            continue

        extracted_item.evidence = validated_evidence
        filtered_values.append(extracted_item)

    extraction.extracted = filtered_values


async def extract_document_checklists(case_id: str, documents: List[DocumentReference]) -> ChecklistCollection:
    if not documents:
        return ChecklistCollection(items=[])

    cached, payloads, signature = await _resolve_cached_collection(case_id, documents)
    if cached is not None:
        logger.debug("Checklist extraction cache hit for signature %s", signature)
        return cached

    case_documents_block = _build_case_documents_block(payloads)
    document_catalog_block = _build_document_catalog(payloads)
    items: List[ChecklistItemResult] = []
    text_lookup = {payload["id"]: payload["text"] for payload in payloads}

    async def _extract_item(name: str, desc: str) -> ChecklistItemResult:
        prompt = (
            _DOCUMENT_PROMPT_TEMPLATE.replace("{item_description}", desc)
            .replace("{document_catalog}", document_catalog_block)
            .replace("{case_documents}", case_documents_block)
        )
        try:
            extraction = await llm_service.generate_structured(
                prompt,
                response_model=ChecklistExtractionPayload,
            )
            _validate_evidence_offsets(name, extraction, text_lookup)
        except Exception:  # pylint: disable=broad-except
            logger.exception("Failed to extract checklist item '%s' for case %s", name, case_id)
            raise
        return ChecklistItemResult(item_name=name, extraction=extraction)

    tasks = [
        asyncio.create_task(_extract_item(item_name, description))
        for item_name, description in _CHECKLIST_ITEM_DESCRIPTIONS.items()
    ]

    try:
        gathered = await asyncio.gather(*tasks)
    except Exception:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise

    items = list(gathered)
    results = ChecklistCollection(items=items)
    try:
        _DOCUMENT_CHECKLIST_STORE.set(case_id, signature=signature, items=results)
    except Exception:  # pylint: disable=broad-except
        logger.exception("Failed to persist checklist results for case %s", case_id)

    async with _DOCUMENT_CACHE_LOCK:
        cached = _DOCUMENT_CACHE.get(signature)
        if cached is None:
            _DOCUMENT_CACHE[signature] = _copy_collection(results)
            cached = _DOCUMENT_CACHE[signature]

    return _copy_collection(cached)


def _build_summary_prompt(summary_text: str) -> str:
    definitions_lines = [f"{item}: {description}" for item, description in _CHECKLIST_ITEM_DESCRIPTIONS.items()]
    definitions_block = "\n".join(definitions_lines)
    prompt_template = (
        "You are reviewing a draft legal case summary. For each checklist item definition below, extract the"
        " relevant information from the summary using the same JSON schema used for the document-driven extraction."
        " If the summary lacks information for a checklist item, return an empty list for 'extracted' and briefly"
        " explain that in 'reasoning'. Respond with JSON only.\n\n"
        "Checklist item definitions:\n{checklist_definitions}\n\n"
        "Summary:\n{summary_text}\n\n"
        "Return JSON with the following structure:\n"
        "{\n"
        '  "items": [\n'
        "    {\n"
        '      "itemName": "<ChecklistItemName>",\n'
        '      "extraction": {\n'
        '        "reasoning": "<brief justification>",\n'
        '        "extracted": [\n'
        "          {\n"
        '            "value": "<concise value>",\n'
        '            "evidence": [\n'
        "              {\n"
        '                "text": "<exact summary quote>",\n'
        f'                "documentId": {SUMMARY_DOCUMENT_ID},\n'
        '                "startOffset": <integer start offset>\n'
        "              }\n"
        "            ]\n"
        "          }\n"
        "        ]\n"
        "      }\n"
        "    }\n"
        "  ]\n"
        "}\n"
    )

    return (
        prompt_template.replace("{checklist_definitions}", definitions_block).replace(
            "{summary_text}", _truncate_text(summary_text, _MAX_SUMMARY_CHARS)
        )
    )


async def extract_summary_checklists(summary_text: str) -> ChecklistCollection:
    if not summary_text.strip():
        return ChecklistCollection(
            items=[
                ChecklistItemResult(
                    item_name=item,
                    extraction=ChecklistExtractionPayload(
                        reasoning="Summary text was empty.",
                        extracted=[],
                    ),
                )
                for item in _CHECKLIST_ITEM_DESCRIPTIONS
            ]
        )

    prompt = _build_summary_prompt(summary_text)
    try:
        response = await llm_service.generate_structured(
            prompt,
            response_model=SummaryChecklistExtractionPayload,
        )
        text_lookup = {SUMMARY_DOCUMENT_ID: summary_text}
        for item in response.items:
            _validate_evidence_offsets(item.item_name, item.extraction, text_lookup)
    except Exception:  # pylint: disable=broad-except
        logger.exception("Failed to extract checklist items from summary")
        raise

    by_name = {item.item_name: item.extraction for item in response.items}
    normalized_items: List[ChecklistItemResult] = []
    for item_name in _CHECKLIST_ITEM_DESCRIPTIONS:
        extraction = by_name.get(
            item_name,
            ChecklistExtractionPayload(reasoning="", extracted=[]),
        )
        normalized_items.append(ChecklistItemResult(item_name=item_name, extraction=extraction))

    return ChecklistCollection(items=normalized_items)
