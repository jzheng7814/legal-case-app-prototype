from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from .documents import DocumentReference


class ChatMessageRole(str, Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


class ChatMessage(BaseModel):
    id: str
    role: ChatMessageRole
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ChatContextItem(BaseModel):
    type: str
    document_id: Optional[int] = Field(
        default=None,
        serialization_alias="documentId",
        validation_alias=AliasChoices("document_id", "documentId"),
    )
    summary_snippet: Optional[str] = None
    highlight_text: Optional[str] = None
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ChatSession(BaseModel):
    id: str
    title: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    messages: List[ChatMessage] = Field(default_factory=list)
    context: List[ChatContextItem] = Field(default_factory=list)
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class CreateChatSessionResponse(BaseModel):
    session: ChatSession
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ChatMessageRequest(BaseModel):
    message: str
    context: Optional[List[ChatContextItem]] = None
    documents: Optional[List[DocumentReference]] = None
    summary_text: Optional[str] = Field(
        None,
        serialization_alias="summaryText",
        validation_alias=AliasChoices("summaryText", "summary_text"),
    )
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class SummaryPatch(BaseModel):
    start_index: int = Field(
        ...,
        serialization_alias="startIndex",
        validation_alias=AliasChoices("startIndex", "start_index"),
    )
    delete_count: int = Field(
        ...,
        serialization_alias="deleteCount",
        validation_alias=AliasChoices("deleteCount", "delete_count"),
    )
    insert_text: str = Field(
        default="",
        serialization_alias="insertText",
        validation_alias=AliasChoices("insertText", "insert_text"),
    )
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ChatMessageResponse(BaseModel):
    session_id: str = Field(
        ...,
        serialization_alias="sessionId",
        validation_alias=AliasChoices("sessionId", "session_id"),
    )
    messages: List[ChatMessage]
    summary_update: Optional[str] = Field(
        default=None,
        serialization_alias="summaryUpdate",
        validation_alias=AliasChoices("summaryUpdate", "summary_update"),
    )
    summary_patches: Optional[List[SummaryPatch]] = Field(
        default=None,
        serialization_alias="summaryPatches",
        validation_alias=AliasChoices("summaryPatches", "summary_patches"),
    )
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
