from fastapi import APIRouter

from app.schemas.suggestions import SuggestionRequest, SuggestionResponse
from app.services.suggestions import generate_suggestions

router = APIRouter(prefix="/cases", tags=["cases"])


@router.post("/{case_id}/suggestions", response_model=SuggestionResponse)
async def generate_case_suggestions(case_id: str, request: SuggestionRequest) -> SuggestionResponse:
    return await generate_suggestions(case_id, request)
