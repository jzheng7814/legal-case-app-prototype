from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

from .documents import DocumentReference
from .checklists import ChecklistBinCollection, ChecklistCollection


class SuggestionType(str, Enum):
    edit = "edit"
    addition = "addition"
    deletion = "deletion"


class TextRange(BaseModel):
    start: int = Field(..., ge=0)
    end: int = Field(..., ge=0)
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @model_validator(mode='after')
    def check_range(self):
        if self.end < self.start:
            raise ValueError("end must be greater than or equal to start")
        return self


class Suggestion(BaseModel):
    id: str
    type: SuggestionType
    comment: str
    source_document: Optional[str] = Field(
        None,
        serialization_alias="sourceDocument",
        validation_alias=AliasChoices("sourceDocument", "source_document"),
    )
    original_text: Optional[str] = Field(
        None,
        serialization_alias="originalText",
        validation_alias=AliasChoices("originalText", "original_text"),
    )
    text: Optional[str] = None
    position: Optional[TextRange] = None
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class SuggestionRequest(BaseModel):
    summary_text: str = Field(
        ...,
        serialization_alias="summaryText",
        validation_alias=AliasChoices("summaryText", "summary_text"),
    )
    documents: List[DocumentReference]
    max_suggestions: int = Field(
        ...,
        serialization_alias="maxSuggestions",
        validation_alias=AliasChoices("maxSuggestions", "max_suggestions"),
        ge=1,
        le=20,
    )
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class SuggestionResponse(BaseModel):
    suggestions: List[Suggestion]
    document_checklists: ChecklistBinCollection = Field(
        serialization_alias="documentChecklists",
        validation_alias=AliasChoices("documentChecklists", "document_checklists"),
    )
    summary_checklists: ChecklistCollection = Field(
        serialization_alias="summaryChecklists",
        validation_alias=AliasChoices("summaryChecklists", "summary_checklists"),
    )
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class SuggestionValidationResult(BaseModel):
    valid: bool
    suggestions: List[Suggestion]
    errors: List[str]
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class SuggestionGenerationPayload(BaseModel):
    suggestions: List[Suggestion]
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
