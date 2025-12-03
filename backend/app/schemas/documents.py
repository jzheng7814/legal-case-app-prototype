from __future__ import annotations

from typing import List, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from .checklists import ChecklistBinCollection


class DocumentMetadata(BaseModel):
    id: int = Field(..., description="Stable identifier for the document")
    title: str = Field(..., description="Human-readable title for display")
    type: Optional[str] = Field(None, description="Document type or classifier label")
    description: Optional[str] = None
    source: Optional[str] = Field(None, description="Where the document was obtained from")
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Document(DocumentMetadata):
    content: str = Field(..., description="Full document body as plain text")
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class DocumentListResponse(BaseModel):
    case_id: str
    documents: List[Document]
    document_checklists: Optional[ChecklistBinCollection] = Field(
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
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class DocumentChunk(BaseModel):
    id: str
    text: str
    start: int
    end: int
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
