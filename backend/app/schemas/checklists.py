from __future__ import annotations

from typing import List, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

SUMMARY_DOCUMENT_ID = -1


class ChecklistEvidence(BaseModel):
    text: Optional[str] = None
    document_id: int = Field(
        ...,
        serialization_alias="documentId",
        validation_alias=AliasChoices("document_id", "documentId", "source_document", "sourceDocument"),
    )
    start_offset: int | None = Field(
        None,
        ge=0,
        serialization_alias="startOffset",
        validation_alias=AliasChoices("start_offset", "startOffset"),
    )
    end_offset: int | None = Field(
        None,
        ge=0,
        serialization_alias="endOffset",
        validation_alias=AliasChoices("end_offset", "endOffset"),
    )
    sentence_ids: Optional[List[int]] = Field(
        default=None,
        serialization_alias="sentenceIds",
        validation_alias=AliasChoices("sentenceIds", "sentence_ids"),
        exclude=True,
    )
    verified: bool = Field(
        True,
        serialization_alias="verified",
        validation_alias=AliasChoices("verified",),
    )

    @field_validator("document_id", mode="before")
    @classmethod
    def _require_integer_document_id(cls, value: object) -> int:
        if isinstance(value, int):
            return value
        raise TypeError("document_id must be provided as an integer")

    @field_validator("sentence_ids", mode="before")
    @classmethod
    def _coerce_sentence_ids(cls, value: object) -> Optional[List[int]]:
        if value is None:
            return None
        if isinstance(value, (list, tuple)):
            result: List[int] = []
            for entry in value:
                if not isinstance(entry, int):
                    raise TypeError("sentence_ids must be a list of integers")
                result.append(entry)
            return result
        raise TypeError("sentence_ids must be provided as a list of integers")

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ChecklistValue(BaseModel):
    value: str
    evidence: List[ChecklistEvidence]

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ChecklistExtractionPayload(BaseModel):
    reasoning: str
    extracted: List[ChecklistValue]

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ChecklistItemResult(BaseModel):
    item_name: str = Field(
        ...,
        serialization_alias="itemName",
        validation_alias=AliasChoices("itemName", "item_name", "name"),
    )
    extraction: ChecklistExtractionPayload = Field(
        ...,
        serialization_alias="extraction",
        validation_alias=AliasChoices("extraction", "result", "payload"),
    )

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ChecklistCollection(BaseModel):
    items: List[ChecklistItemResult] = Field(
        ...,
        serialization_alias="items",
        validation_alias=AliasChoices("items", "entries"),
    )

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class SummaryChecklistExtractionPayload(ChecklistCollection):
    """Structured output for summary-driven checklist extraction."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ChecklistSentenceEvidence(BaseModel):
    document_id: int = Field(
        ...,
        serialization_alias="documentId",
        validation_alias=AliasChoices("documentId", "document_id"),
    )
    sentence_ids: List[int] = Field(
        ...,
        serialization_alias="sentenceIds",
        validation_alias=AliasChoices("sentenceIds", "sentence_ids"),
        min_length=1,
    )

    @field_validator("sentence_ids", mode="before")
    @classmethod
    def _coerce_sentence_ids(cls, value: object) -> List[int]:
        if isinstance(value, (list, tuple)):
            result: List[int] = []
            for entry in value:
                if not isinstance(entry, int):
                    raise TypeError("sentence_ids must be a list of integers")
                result.append(entry)
            return result
        raise TypeError("sentence_ids must be a list of integers")

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ChecklistBinValue(BaseModel):
    value: str
    evidence: List[ChecklistEvidence]

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ChecklistBinExtractionPayload(BaseModel):
    reasoning: str
    extracted: List[ChecklistBinValue]

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ChecklistBinResult(BaseModel):
    bin_id: str = Field(
        ...,
        serialization_alias="binId",
        validation_alias=AliasChoices("bin_id", "binId", "id"),
    )
    extraction: ChecklistBinExtractionPayload = Field(
        ...,
        serialization_alias="extraction",
        validation_alias=AliasChoices("extraction", "result", "payload"),
    )

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ChecklistBinCollection(BaseModel):
    bins: List[ChecklistBinResult] = Field(
        ...,
        serialization_alias="bins",
        validation_alias=AliasChoices("bins", "items", "entries"),
    )

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ChecklistCategoryValue(BaseModel):
    id: str
    value: str
    text: Optional[str] = None
    document_id: Optional[int] = Field(
        None,
        serialization_alias="documentId",
        validation_alias=AliasChoices("documentId", "document_id"),
    )
    start_offset: Optional[int] = Field(
        None,
        ge=0,
        serialization_alias="startOffset",
        validation_alias=AliasChoices("startOffset", "start_offset"),
    )
    end_offset: Optional[int] = Field(
        None,
        ge=0,
        serialization_alias="endOffset",
        validation_alias=AliasChoices("endOffset", "end_offset"),
    )

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ChecklistCategory(BaseModel):
    id: str
    label: str
    color: str
    values: List[ChecklistCategoryValue] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ChecklistCategoryCollection(BaseModel):
    signature: str
    categories: List[ChecklistCategory]

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ChecklistStatusResponse(BaseModel):
    checklist_status: str = Field(
        ...,
        serialization_alias="checklistStatus",
        validation_alias=AliasChoices("checklistStatus", "checklist_status"),
    )
    document_checklists: Optional[ChecklistBinCollection] = Field(
        default=None,
        serialization_alias="documentChecklists",
        validation_alias=AliasChoices("documentChecklists", "document_checklists"),
    )

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ChecklistItemCreateRequest(BaseModel):
    category_id: str = Field(..., serialization_alias="categoryId", validation_alias=AliasChoices("categoryId", "category_id"))
    text: str
    document_id: Optional[int] = Field(
        None,
        serialization_alias="documentId",
        validation_alias=AliasChoices("documentId", "document_id"),
    )
    start_offset: Optional[int] = Field(
        None,
        ge=0,
        serialization_alias="startOffset",
        validation_alias=AliasChoices("startOffset", "start_offset"),
    )
    end_offset: Optional[int] = Field(
        None,
        ge=0,
        serialization_alias="endOffset",
        validation_alias=AliasChoices("endOffset", "end_offset"),
    )

    @property
    def value(self) -> str:
        return self.text

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
