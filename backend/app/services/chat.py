from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Dict, List

from fastapi import HTTPException

from app.schemas.chat import (
    ChatMessage,
    ChatMessageRequest,
    ChatMessageResponse,
    ChatMessageRole,
    ChatSession,
    ChatContextItem,
)
from app.services.llm import LLMMessage, llm_service

_chat_sessions: Dict[str, ChatSession] = {}
_chat_lock = asyncio.Lock()

_SYSTEM_PROMPT = (
    "You are an expert legal writing assistant providing precise and concise guidance. "
    "Ground every response in the supplied summary, documents, highlights, and prior suggestions. "
    "Cite document ids when relevant and keep answers direct."
)


async def create_session() -> ChatSession:
    session_id = str(uuid.uuid4())
    session = ChatSession(id=session_id, title=f"Session {datetime.utcnow():%Y-%m-%d %H:%M:%S}", messages=[], context=[])
    async with _chat_lock:
        _chat_sessions[session_id] = session
    return session


async def get_session(session_id: str) -> ChatSession:
    async with _chat_lock:
        session = _chat_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return session


async def list_sessions() -> List[ChatSession]:
    async with _chat_lock:
        return list(_chat_sessions.values())


async def post_message(session_id: str, payload: ChatMessageRequest) -> ChatMessageResponse:
    session = await get_session(session_id)

    user_message = ChatMessage(id=str(uuid.uuid4()), role=ChatMessageRole.user, content=payload.message)
    context = payload.context or []
    updated_context = session.context + context

    llm_messages = [
        LLMMessage(role=message.role.value, content=message.content)
        for message in session.messages[-12:]
    ]
    llm_messages.append(
        LLMMessage(
            role="user",
            content=_compose_user_content(user_message.content, payload, updated_context),
        )
    )

    response_text = await llm_service.chat(llm_messages, system=_SYSTEM_PROMPT)

    assistant_message = ChatMessage(id=str(uuid.uuid4()), role=ChatMessageRole.assistant, content=response_text.strip())

    updated_messages = session.messages + [user_message, assistant_message]
    updated_session = session.model_copy(update={"messages": updated_messages, "context": updated_context})

    async with _chat_lock:
        _chat_sessions[session_id] = updated_session

    return ChatMessageResponse(session_id=session_id, messages=[user_message, assistant_message])


def _compose_user_content(message: str, payload: ChatMessageRequest, context: List[ChatContextItem]) -> str:
    segments: List[str] = [message.strip()]
    context_lines: List[str] = []
    if payload.summary_text:
        context_lines.append(f"Summary:\n{payload.summary_text}")
    if payload.documents:
        for doc in payload.documents:
            if doc.content:
                context_lines.append(f"Document {doc.id}: {doc.content[:1500]}")
    for item in context:
        if item.highlight_text:
            context_lines.append(f"Highlight from {item.document_id or 'summary'}: {item.highlight_text}")
        if item.summary_snippet:
            context_lines.append(f"Prior suggestion: {item.summary_snippet}")

    if context_lines:
        segments.append("Context:\n" + "\n\n".join(context_lines))
    return "\n\n".join(segment for segment in segments if segment).strip()
