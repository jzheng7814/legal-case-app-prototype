from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from .documents import DocumentReference


class SuggestionType(str, Enum):
    edit = "edit"
    addition = "addition"
    deletion = "deletion"


class TextRange(BaseModel):
    start: int = Field(..., ge=0)
    end: int = Field(..., ge=0)

    @field_validator("end")
    @classmethod
    def validate_range(cls, end: int, values: dict[str, int]) -> int:
        start = values.get("start", 0)
        if end < start:
            raise ValueError("end must be greater than or equal to start")
        return end


class Suggestion(BaseModel):
    id: str
    type: SuggestionType
    comment: str
    source_document: Optional[str] = Field(None, alias="sourceDocument")
    original_text: Optional[str] = Field(None, alias="originalText")
    suggested_text: Optional[str] = Field(None, alias="suggestedText")
    text: Optional[str] = None
    position: Optional[TextRange] = None


class SuggestionRequest(BaseModel):
    summary_text: str = Field(..., alias="summaryText")
    documents: List[DocumentReference]
    max_suggestions: int = Field(5, alias="maxSuggestions", ge=1, le=20)


class SuggestionResponse(BaseModel):
    suggestions: List[Suggestion]


class SuggestionValidationResult(BaseModel):
    valid: bool
    suggestions: List[Suggestion]
    errors: List[str] = []
