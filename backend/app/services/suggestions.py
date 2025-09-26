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
        "type": "object",
        "required": ["suggestions"],
        "properties": {
            "suggestions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["id", "type", "comment"],
                    "properties": {
                        "id": {"type": "string"},
                        "type": {"type": "string"},
                        "comment": {"type": "string"},
                        "sourceDocument": {"type": "string"},
                        "originalText": {"type": "string"},
                        "suggestedText": {"type": "string"},
                        "text": {"type": "string"},
                        "position": {
                            "type": "object",
                            "properties": {
                                "start": {"type": "integer", "minimum": 0},
                                "end": {"type": "integer", "minimum": 0},
                            },
                        },
                    },
                },
            }
        },
    }
)


async def generate_suggestions(case_id: str, request: SuggestionRequest) -> SuggestionResponse:
    documents_desc = ", ".join(doc.id for doc in request.documents)
    prompt = (
        "You are an expert legal copy editor. Based on the summary and supporting documents, "
        "propose high-impact edits. Each suggestion must target a unique, non-overlapping span of text.\n\n"
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
    if not validation.valid:
        raise HTTPException(status_code=400, detail={"errors": validation.errors})

    limited = suggestions[: request.max_suggestions]
    return SuggestionResponse(suggestions=limited)


def validate_suggestions(suggestions: List[Suggestion]) -> SuggestionValidationResult:
    errors: List[str] = []
    spans = []
    for suggestion in suggestions:
        if suggestion.position:
            spans.append((suggestion.position.start, suggestion.position.end, suggestion.id))

    spans.sort(key=lambda item: item[0])
    for index in range(1, len(spans)):
        prev_start, prev_end, prev_id = spans[index - 1]
        current_start, current_end, current_id = spans[index]
        if current_start < prev_end:
            errors.append(
                f"Suggestions '{prev_id}' and '{current_id}' overlap at characters {current_start}-{prev_end}."
            )

    return SuggestionValidationResult(valid=len(errors) == 0, suggestions=suggestions, errors=errors)
