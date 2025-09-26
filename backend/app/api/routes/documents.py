from fastapi import APIRouter

from app.schemas.documents import DocumentListResponse
from app.services.documents import list_documents

router = APIRouter(prefix="/cases", tags=["cases"])


@router.get("/{case_id}/documents", response_model=DocumentListResponse)
async def get_case_documents(case_id: str) -> DocumentListResponse:
    documents = list_documents(case_id)
    return DocumentListResponse(case_id=case_id, documents=documents)
