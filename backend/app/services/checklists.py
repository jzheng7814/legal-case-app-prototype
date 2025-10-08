from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from fastapi import HTTPException

from app.schemas.documents import DocumentReference
from app.services.documents import get_document
from app.services.llm import llm_service

logger = logging.getLogger(__name__)

_DOCUMENT_CHECKLIST_SCHEMA = json.dumps(
    {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "ChecklistExtraction",
        "type": "object",
        "required": ["reasoning", "extracted"],
        "properties": {
            "reasoning": {"type": "string"},
            "extracted": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["value", "evidence"],
                    "properties": {
                        "value": {"type": "string"},
                        "evidence": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["text", "source_document", "location"],
                                "properties": {
                                    "text": {"type": "string"},
                                    "source_document": {"type": "string"},
                                    "location": {"type": "string"},
                                },
                            },
                        },
                    },
                },
            },
        },
    }
)

_SUMMARY_CHECKLIST_SCHEMA = json.dumps(
    {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "SummaryChecklistExtraction",
        "type": "object",
        "required": ["items"],
        "properties": {
            "items": {
                "type": "object",
                "additionalProperties": json.loads(_DOCUMENT_CHECKLIST_SCHEMA),
            }
        },
    }
)

_ASSET_DIR = Path(__file__).resolve().parents[1] / "resources" / "checklists"
_TEMPLATE_PATH = _ASSET_DIR / "general_template.txt"
_ITEM_DESCRIPTIONS_PATH = _ASSET_DIR / "item_specific_info_improved.json"

if not _TEMPLATE_PATH.exists():
    raise RuntimeError(f"Checklist prompt template not found at {_TEMPLATE_PATH}")

if not _ITEM_DESCRIPTIONS_PATH.exists():
    raise RuntimeError(f"Checklist item descriptions not found at {_ITEM_DESCRIPTIONS_PATH}")

_DOCUMENT_PROMPT_TEMPLATE = _TEMPLATE_PATH.read_text(encoding="utf-8")
_CHECKLIST_ITEM_DESCRIPTIONS: Dict[str, str] = json.loads(_ITEM_DESCRIPTIONS_PATH.read_text(encoding="utf-8"))

_DOCUMENT_CACHE: Dict[str, Dict[str, Any]] = {}
_DOCUMENT_CACHE_LOCK = asyncio.Lock()

_MAX_DOCUMENT_CHARS = 12_000
_MAX_SUMMARY_CHARS = 6_000


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
            display_name = doc_ref.alias or doc_ref.id
        else:
            document = get_document(case_id, doc_ref.id)
            text = doc_ref.content or document.content
            display_name = doc_ref.alias or document.name or document.id

        payloads.append(
            {
                "id": doc_ref.id,
                "display_name": display_name,
                "text": text or "",
            }
        )
    return payloads


def _build_case_documents_block(payloads: List[Dict[str, str]]) -> str:
    blocks: List[str] = []
    for payload in payloads:
        truncated = _truncate_text(payload["text"], _MAX_DOCUMENT_CHARS)
        blocks.append(f"Document: {payload['display_name']}\n{truncated}")
    return "\n\n".join(blocks)


def _compute_documents_signature(case_id: str, payloads: List[Dict[str, str]]) -> str:
    digest = hashlib.sha256(case_id.encode("utf-8"))
    for payload in sorted(payloads, key=lambda item: item["id"]):
        digest.update(payload["id"].encode("utf-8"))
        digest.update(payload["display_name"].encode("utf-8"))
        digest.update(payload["text"].encode("utf-8"))
    return digest.hexdigest()


def _clone(data: Dict[str, Any]) -> Dict[str, Any]:
    return json.loads(json.dumps(data))


async def extract_document_checklists(case_id: str, documents: List[DocumentReference]) -> Dict[str, Dict[str, Any]]:
    if not documents:
        return {}

    payloads = _resolve_document_payloads(case_id, documents)
    signature = _compute_documents_signature(case_id, payloads)

    async with _DOCUMENT_CACHE_LOCK:
        cached = _DOCUMENT_CACHE.get(signature)
    if cached is not None:
        logger.debug("Checklist extraction cache hit for signature %s", signature)
        return _clone(cached)

    case_documents_block = _build_case_documents_block(payloads)
    results: Dict[str, Dict[str, Any]] = {}

    for item_name, description in _CHECKLIST_ITEM_DESCRIPTIONS.items():
        prompt = _DOCUMENT_PROMPT_TEMPLATE.replace("{item_description}", description).replace(
            "{case_documents}", case_documents_block
        )
        try:
            extraction = await llm_service.generate_structured(prompt, schema_hint=_DOCUMENT_CHECKLIST_SCHEMA)
        except Exception:  # pylint: disable=broad-except
            logger.exception("Failed to extract checklist item '%s' for case %s", item_name, case_id)
            raise
        results[item_name] = extraction

    async with _DOCUMENT_CACHE_LOCK:
        cached = _DOCUMENT_CACHE.get(signature)
        if cached is None:
            _DOCUMENT_CACHE[signature] = _clone(results)
            cached = _DOCUMENT_CACHE[signature]

    return _clone(cached)


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
        '  "items": {\n'
        '    "<ChecklistItemName>": {\n'
        '      "reasoning": "<brief justification>",\n'
        '      "extracted": [\n'
        "        {\n"
        '          "value": "<concise value>",\n'
        '          "evidence": [\n'
        "            {\n"
        '              "text": "<exact summary quote>",\n'
        '              "source_document": "Summary",\n'
        '              "location": "<sentence or section reference>"\n'
        "            }\n"
        "          ]\n"
        "        }\n"
        "      ]\n"
        "    }\n"
        "  }\n"
        "}\n"
    )

    return (
        prompt_template.replace("{checklist_definitions}", definitions_block).replace(
            "{summary_text}", _truncate_text(summary_text, _MAX_SUMMARY_CHARS)
        )
    )


async def extract_summary_checklists(summary_text: str) -> Dict[str, Dict[str, Any]]:
    if not summary_text.strip():
        return {
            item: {"reasoning": "Summary text was empty.", "extracted": []}
            for item in _CHECKLIST_ITEM_DESCRIPTIONS
        }

    prompt = _build_summary_prompt(summary_text)
    try:
        response = await llm_service.generate_structured(
            prompt,
            schema_hint=_SUMMARY_CHECKLIST_SCHEMA,
        )
    except Exception:  # pylint: disable=broad-except
        logger.exception("Failed to extract checklist items from summary")
        raise

    items = response.get("items", {})
    # Ensure every checklist item has an entry so downstream logic can rely on consistent keys.
    for item in _CHECKLIST_ITEM_DESCRIPTIONS:
        items.setdefault(item, {"reasoning": "", "extracted": []})

    return items
