from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class DocumentMetadata(BaseModel):
    id: str = Field(..., description="Client-side identifier for the document")
    name: str
    type: str
    description: Optional[str] = None
    source: Optional[str] = Field(None, description="Where the document was obtained from")


class Document(DocumentMetadata):
    content: str = Field(..., description="Full document body as plain text")


class DocumentListResponse(BaseModel):
    case_id: str
    documents: List[Document]


class DocumentReference(BaseModel):
    id: str
    alias: Optional[str] = Field(None, description="Optional alternate name to show in prompts")
    include_full_text: bool = Field(False, description="If true, use client-provided content instead of repository lookup")
    content: Optional[str] = Field(None, description="Raw document text supplied by the caller")


class DocumentChunk(BaseModel):
    id: str
    text: str
    start: int
    end: int
