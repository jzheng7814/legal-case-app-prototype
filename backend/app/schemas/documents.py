from __future__ import annotations

from typing import List, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from .checklists import EvidenceCollection


class DocumentMetadata(BaseModel):
    id: int = Field(..., description="Stable identifier for the document")
    title: str = Field(..., description="Human-readable title for display")
    type: Optional[str] = Field(None, description="Document type or classifier label")
    description: Optional[str] = None
    source: Optional[str] = Field(None, description="Where the document was obtained from")
    ecf_number: Optional[str] = Field(
        None,
        description="Docket/ECF number for ordering",
        serialization_alias="ecfNumber",
        validation_alias=AliasChoices("ecf_number", "ecfNumber"),
    )
    date: Optional[str] = Field(
        None,
        description="Filing or decision date (ISO)",
    )
    date_is_estimate: Optional[bool] = Field(
        None,
        description="Whether the filing date is an estimate",
        serialization_alias="dateIsEstimate",
        validation_alias=AliasChoices("dateIsEstimate", "date_is_estimate"),
    )
    date_not_available: Optional[bool] = Field(
        None,
        description="Date missing flag from source",
        serialization_alias="dateNotAvailable",
        validation_alias=AliasChoices("dateNotAvailable", "date_not_available"),
    )
    is_docket: bool = Field(
        False,
        description="True when representing the main docket and should be ordered first",
        serialization_alias="isDocket",
        validation_alias=AliasChoices("isDocket", "is_docket"),
    )
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Document(DocumentMetadata):
    content: str = Field(..., description="Full document body as plain text")
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class DocumentListResponse(BaseModel):
    case_id: str
    documents: List[Document]
    document_checklists: Optional[EvidenceCollection] = Field(
        default=None,
        serialization_alias="documentChecklists",
        validation_alias=AliasChoices("documentChecklists", "document_checklists"),
    )
    checklist_status: str = Field(
        default="idle",
        serialization_alias="checklistStatus",
        validation_alias=AliasChoices("checklistStatus", "checklist_status"),
    )
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class DocumentReference(BaseModel):
    id: int
    title: Optional[str] = Field(None, description="Display title when overriding stored metadata")
    alias: Optional[str] = Field(None, description="Optional alternate name to show in prompts")
    include_full_text: bool = Field(False, description="If true, use client-provided content instead of repository lookup")
    content: Optional[str] = Field(None, description="Raw document text supplied by the caller")
    ecf_number: Optional[str] = Field(
        None,
        serialization_alias="ecfNumber",
        validation_alias=AliasChoices("ecf_number", "ecfNumber"),
    )
    is_docket: bool = Field(
        False,
        serialization_alias="isDocket",
        validation_alias=AliasChoices("isDocket", "is_docket"),
    )
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class DocumentChunk(BaseModel):
    id: str
    text: str
    start: int
    end: int
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
