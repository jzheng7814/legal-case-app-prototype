from fastapi import APIRouter

from app.api.routes import chat, documents, health, suggestions, summary

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(documents.router)
api_router.include_router(summary.router)
api_router.include_router(suggestions.router)
api_router.include_router(chat.router)
