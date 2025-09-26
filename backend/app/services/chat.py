from __future__ import annotations

import asyncio
import textwrap
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
from app.services.llm import llm_service

_chat_sessions: Dict[str, ChatSession] = {}
_chat_lock = asyncio.Lock()


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

    prompt = _build_prompt(session, user_message, payload, updated_context)
    response_text = await llm_service.generate_text(prompt)

    assistant_message = ChatMessage(id=str(uuid.uuid4()), role=ChatMessageRole.assistant, content=response_text.strip())

    updated_messages = session.messages + [user_message, assistant_message]
    updated_session = session.model_copy(update={"messages": updated_messages, "context": updated_context})

    async with _chat_lock:
        _chat_sessions[session_id] = updated_session

    return ChatMessageResponse(session_id=session_id, messages=[user_message, assistant_message])


def _build_prompt(
    session: ChatSession,
    user_message: ChatMessage,
    payload: ChatMessageRequest,
    context: List[ChatContextItem],
) -> str:
    history_fragment = "\n\n".join(
        f"{message.role.value.upper()}: {message.content}" for message in session.messages[-6:]
    )

    context_lines = []
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

    context_block = "\n\n".join(context_lines)

    prompt = textwrap.dedent(
        f"""
        You are an expert legal writing assistant providing precise and concise guidance.\n
        Conversation history (most recent first):\n{history_fragment}\n
        Additional context:\n{context_block}\n
        User asks: {user_message.content}\n
        Provide a direct answer grounded in the supplied materials. Offer actionable steps and cite relevant documents by id when applicable.
        """
    )
    return prompt
