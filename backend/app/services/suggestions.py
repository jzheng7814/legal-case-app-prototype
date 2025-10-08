from __future__ import annotations

import json
import logging
from typing import List

from fastapi import HTTPException

from app.schemas.suggestions import Suggestion, SuggestionRequest, SuggestionResponse, SuggestionValidationResult
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
                        "suggestedText": {"type": "string"},
                        "text": {"type": "string"},
                        "position": {
                            "title": "TextRange",
                            "type": "object",
                            "required": ["start", "end"],
                            "properties": {
                                "start": {"type": "integer", "minimum": 0},
                                "end": {"type": "integer", "minimum": 0}
                            }
                        }
                    }
                }
            }
        }
    }
)


async def generate_suggestions(case_id: str, request: SuggestionRequest) -> SuggestionResponse:
    documents_desc = ", ".join(doc.id for doc in request.documents)
    prompt = (
        "You are an expert legal copy editor. Based on the summary and supporting documents, "
        "propose high-impact edits. Each suggestion must target a unique, non-overlapping span of text."
        "Do NOT reason, plan, or think step-by-step, except to check that your output matches the required schema exactly, down to the field names and types.\n\n"
        f"Summary:\n{request.summary_text}\n\n"
        f"Documents referenced: {documents_desc}."
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
    return SuggestionResponse(suggestions=limited)


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
