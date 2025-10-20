from __future__ import annotations

from typing import List

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class ChecklistEvidence(BaseModel):
    text: str
    source_document: str = Field(
        ...,
        validation_alias=AliasChoices("source_document", "sourceDocument"),
    )
    location: str

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
