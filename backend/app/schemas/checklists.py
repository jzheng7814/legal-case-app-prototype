from __future__ import annotations

from typing import List

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

SUMMARY_DOCUMENT_ID = -1


class ChecklistEvidence(BaseModel):
    text: str
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
