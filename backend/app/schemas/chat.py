from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

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


class ChatContextItem(BaseModel):
    type: str
    document_id: Optional[str] = None
    summary_snippet: Optional[str] = None
    highlight_text: Optional[str] = None


class ChatSession(BaseModel):
    id: str
    title: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    messages: List[ChatMessage] = Field(default_factory=list)
    context: List[ChatContextItem] = Field(default_factory=list)


class CreateChatSessionResponse(BaseModel):
    session: ChatSession


class ChatMessageRequest(BaseModel):
    message: str
    context: Optional[List[ChatContextItem]] = None
    documents: Optional[List[DocumentReference]] = None
    summary_text: Optional[str] = Field(None, alias="summaryText")


class ChatMessageResponse(BaseModel):
    session_id: str = Field(..., alias="sessionId")
    messages: List[ChatMessage]
