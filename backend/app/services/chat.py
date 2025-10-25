from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from difflib import SequenceMatcher
from typing import Dict, List

from fastapi import HTTPException

from app.schemas.chat import (
    ChatContextItem,
    ChatMessage,
    ChatMessageRequest,
    ChatMessageResponse,
    ChatMessageRole,
    ChatSession,
    SummaryPatch,
)
from app.services.llm import LLMMessage, LLMToolCall, LLMToolHandlerResult, llm_service

_chat_sessions: Dict[str, ChatSession] = {}
_chat_lock = asyncio.Lock()

_SYSTEM_PROMPT = (
    "You are an expert legal writing assistant supporting attorneys. "
    "Use the supplied summary, documents, highlights, and prior suggestions as the source of truth for every answer. "
    "When the user explicitly asks you to revise, improve, or rewrite the case summary, draft a refreshed version that reflects the discussion and context. "
    "Use the commit_summary_edit function to provide the complete updated summary once it is finalized so the workspace stays in sync. "
    "After submitting the tool call, summarize the specific changes and rationale instead of re-pasting the full summary into your chat reply."
)
SUMMARY_DOCUMENT_ID = -1

_SUMMARY_EDIT_TOOLS = [
    {
        "type": "function",
        "name": "commit_summary_edit",
        "description": (
            "Submit a refreshed case summary when the attorney asks for revisions."
            "Provide the full summary text exactly as it should appear in the workspace."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "summary_text": {
                    "type": "string",
                    "description": "The complete updated case summary in final prose form.",
                }
            },
            "required": ["summary_text"],
        },
    }
]


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

    llm_result = await llm_service.chat_with_tools(
        llm_messages,
        system=_SYSTEM_PROMPT,
        tools=_SUMMARY_EDIT_TOOLS,
        tool_handler=_handle_summary_tool_call,
    )
    summary_update = _summary_update_from_tool_outputs(llm_result.tool_outputs)
    summary_patches: List[SummaryPatch] | None = None
    if summary_update is not None and payload.summary_text is not None:
        summary_patches = _build_summary_patches(payload.summary_text, summary_update)

    assistant_message = ChatMessage(id=str(uuid.uuid4()), role=ChatMessageRole.assistant, content=llm_result.text.strip())

    updated_messages = session.messages + [user_message, assistant_message]
    updated_session = session.model_copy(update={"messages": updated_messages, "context": updated_context})

    async with _chat_lock:
        _chat_sessions[session_id] = updated_session

    return ChatMessageResponse(
        session_id=session_id,
        messages=[user_message, assistant_message],
        summary_update=summary_update,
        summary_patches=summary_patches,
    )


def _compose_user_content(message: str, payload: ChatMessageRequest, context: List[ChatContextItem]) -> str:
    segments: List[str] = [message.strip()]
    context_lines: List[str] = []
    if payload.summary_text:
        context_lines.append(f"Summary:\n{payload.summary_text}")
    if payload.documents:
        for doc in payload.documents:
            if doc.content:
                title = getattr(doc, "title", None) or getattr(doc, "alias", None)
                header = f"Document {doc.id}"
                if title:
                    header += f" — {title}"
                context_lines.append(f"{header}:\n{doc.content[:1500]}")
            else:
                title = getattr(doc, "title", None) or getattr(doc, "alias", None)
                header = f"Document {doc.id}"
                if title:
                    header += f" — {title}"
                context_lines.append(header)
    for item in context:
        if item.highlight_text:
            if item.document_id is None or item.document_id == SUMMARY_DOCUMENT_ID:
                source_label = "summary"
            else:
                source_label = f"Document {item.document_id}"
            context_lines.append(f"Highlight from {source_label}: {item.highlight_text}")
        if item.summary_snippet:
            context_lines.append(f"Prior suggestion: {item.summary_snippet}")

    if context_lines:
        segments.append("Context:\n" + "\n\n".join(context_lines))
    return "\n\n".join(segment for segment in segments if segment).strip()


def _parse_summary_tool_arguments(arguments: str | None) -> str | None:
    if not arguments:
        return None
    try:
        payload = json.loads(arguments)
    except (json.JSONDecodeError, TypeError):
        return None
    summary_text = payload.get("summary_text") or payload.get("summaryText")
    if isinstance(summary_text, str):
        stripped = summary_text.strip()
        return stripped or None
    return None


def _summary_update_from_tool_outputs(results: List[LLMToolHandlerResult]) -> str | None:
    latest: str | None = None
    for result in results:
        metadata = result.metadata or {}
        summary_text = metadata.get("summary_text")
        if isinstance(summary_text, str) and summary_text.strip():
            latest = summary_text.strip()
    return latest


async def _handle_summary_tool_call(tool_call: LLMToolCall) -> LLMToolHandlerResult:
    summary_text = _parse_summary_tool_arguments(tool_call.arguments)
    if not summary_text:
        output = json.dumps({
            "status": "error",
            "message": "summary_text is required",
        })
        return LLMToolHandlerResult(call=tool_call, output=output, metadata={"error": "missing_summary"})

    output = json.dumps({"status": "committed", "length": len(summary_text)})
    return LLMToolHandlerResult(call=tool_call, output=output, metadata={"summary_text": summary_text})


def _build_summary_patches(previous_text: str, updated_text: str) -> List[SummaryPatch]:
    if previous_text is None:
        return []
    matcher = SequenceMatcher(a=previous_text, b=updated_text, autojunk=False)
    patches: List[SummaryPatch] = []
    for tag, start_old, end_old, start_new, end_new in matcher.get_opcodes():
        if tag == "equal":
            continue
        delete_count = end_old - start_old if tag in {"replace", "delete"} else 0
        insert_text = updated_text[start_new:end_new] if tag in {"replace", "insert"} else ""
        patches.append(
            SummaryPatch(
                start_index=start_old,
                delete_count=delete_count,
                insert_text=insert_text,
            )
        )
    return patches
