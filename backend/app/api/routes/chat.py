from fastapi import APIRouter

from app.schemas.chat import ChatMessageRequest, ChatMessageResponse, CreateChatSessionResponse
from app.services import chat as chat_service

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/session", response_model=CreateChatSessionResponse)
async def create_session() -> CreateChatSessionResponse:
    session = await chat_service.create_session()
    return CreateChatSessionResponse(session=session)


@router.get("/session/{session_id}")
async def get_session(session_id: str):
    session = await chat_service.get_session(session_id)
    return {"session": session}


@router.post("/session/{session_id}/message", response_model=ChatMessageResponse)
async def send_message(session_id: str, payload: ChatMessageRequest) -> ChatMessageResponse:
    return await chat_service.post_message(session_id, payload)
