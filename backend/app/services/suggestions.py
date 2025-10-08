from __future__ import annotations

import asyncio
import json
import logging
from typing import List

from fastapi import HTTPException

from app.schemas.suggestions import Suggestion, SuggestionRequest, SuggestionResponse, SuggestionValidationResult
from app.services.checklists import extract_document_checklists, extract_summary_checklists, get_checklist_definitions
from app.services.llm import llm_service

logger = logging.getLogger(__name__)

_SUGGESTION_JSON_SCHEMA = json.dumps(
    {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "SuggestionResponse",
        "type": "object",
        "required": ["suggestions"],
        "properties": {
            "suggestions": {
                "type": "array",
                "items": {
                    "title": "Suggestion",
                    "type": "object",
                    "required": ["id", "type", "comment"],
                    "properties": {
                        "id": {"type": "string"},
                        "type": {
                            "type": "string",
                            "enum": ["edit", "addition", "deletion"]
                        },
                        "comment": {"type": "string"},
                        "sourceDocument": {"type": "string"},
                        "originalText": {"type": "string"},
                        "text": {"type": "string"},
                        "position": {
                            "title": "TextRange",
                            "type": "object",
                            "required": ["start", "end"],
                            "properties": {
                                "start": {"type": "integer", "minimum": 0},
                                "end": {"type": "integer", "minimum": 0}
                            },
                            "additionalProperties": False
                        }
                    },
                    "additionalProperties": False
                }
            }
        },
        "additionalProperties": False
    }
)


async def generate_suggestions(case_id: str, request: SuggestionRequest) -> SuggestionResponse:
    documents_desc = ", ".join(doc.id for doc in request.documents) or "none supplied"
    try:
        # Extract checklist information in parallel so we only call the expensive workflow when needed.
        document_checklists, summary_checklists = await asyncio.gather(
            extract_document_checklists(case_id, request.documents),
            extract_summary_checklists(request.summary_text),
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Checklist extraction failed")
        raise HTTPException(status_code=500, detail=f"Failed to extract checklist items: {exc}") from exc

    definitions_json = json.dumps(get_checklist_definitions(), indent=2)
    document_checklists_json = json.dumps(document_checklists, indent=2)
    summary_checklists_json = json.dumps(summary_checklists, indent=2)

    prompt = (
        "You are an expert legal copy editor. Use the checklist extracted from the source documents as the ground"
        " truth for what the summary must cover. Compare it to the checklist extracted from the current summary to"
        " spot missing content, inaccuracies, and opportunities to improve precision. Recommend high-impact edits to"
        " the summary that address those issues. For each suggestion comment, explicitly mention the checklist gap or"
        " discrepancy it resolves. Each suggestion must target a unique, non-overlapping span of text."
        " Do NOT reason, plan, or think step-by-step, except to verify your JSON matches the required schema exactly,"
        " down to field names and types.\n\n"
        f"Documents referenced: {documents_desc}.\n\n"
        f"Checklist definitions:\n{definitions_json}\n\n"
        f"Checklist derived from source documents:\n{document_checklists_json}\n\n"
        f"Checklist derived from current summary:\n{summary_checklists_json}\n\n"
        f"Current summary text:\n{request.summary_text}\n"
    )

    try:
        raw = await llm_service.generate_structured(prompt, schema_hint=_SUGGESTION_JSON_SCHEMA)
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("LLM suggestion generation failed")
        raise HTTPException(status_code=500, detail=f"Failed to generate suggestions: {exc}") from exc

    suggestions_payload = raw.get("suggestions", [])
    suggestions = [Suggestion.model_validate(item) for item in suggestions_payload]
    validation = validate_suggestions(suggestions)
    if validation.errors:
        logger.warning("Discarded %d overlapping suggestions", len(validation.errors))

    limited = validation.suggestions[: request.max_suggestions]
    serialized_suggestions = [suggestion.model_dump(by_alias=True) for suggestion in limited]
    response_payload = {
        "suggestions": serialized_suggestions,
        "documentChecklists": document_checklists,
        "summaryChecklists": summary_checklists,
    }
    return response_payload


def validate_suggestions(suggestions: List[Suggestion]) -> SuggestionValidationResult:
    errors: List[str] = []
    spans = []
    for index, suggestion in enumerate(suggestions):
        if suggestion.position:
            spans.append((suggestion.position.start, suggestion.position.end, index))

    spans.sort(key=lambda item: (item[0], item[2]))
    keep_indices = set(range(len(suggestions)))
    active_span = None

    for start, end, index in spans:
        if active_span is None:
            active_span = (start, end, index)
            continue

        active_start, active_end, active_index = active_span
        if start < active_end:
            keep_indices.discard(index)
            errors.append(
                f"Discarded suggestion '{suggestions[index].id}' due to overlap with '{suggestions[active_index].id}'."
            )
            continue

        active_span = (start, end, index)

    filtered = [suggestion for idx, suggestion in enumerate(suggestions) if idx in keep_indices]

    return SuggestionValidationResult(valid=True, suggestions=filtered, errors=errors)
