from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.schemas.summary import SummaryJobEnvelope, SummaryPromptResponse, SummaryRequest
from app.services import summary as summary_service

router = APIRouter(prefix="/cases", tags=["cases"])


@router.post("/{case_id}/summary", response_model=SummaryJobEnvelope)
async def start_summary_job(case_id: str, request: SummaryRequest, background: BackgroundTasks) -> SummaryJobEnvelope:
    job = await summary_service.create_summary_job(case_id, request, background)
    return SummaryJobEnvelope(job=job)


@router.get("/{case_id}/summary/{job_id}", response_model=SummaryJobEnvelope)
async def get_summary_job(case_id: str, job_id: str) -> SummaryJobEnvelope:
    job = await summary_service.get_summary_job(job_id)
    if job.case_id != case_id:
        raise HTTPException(status_code=404, detail="Summary job not found for case")
    return SummaryJobEnvelope(job=job)


@router.get("/summary/prompt", response_model=SummaryPromptResponse)
async def get_summary_prompt() -> SummaryPromptResponse:
    prompt = summary_service.get_default_summary_prompt()
    return SummaryPromptResponse(prompt=prompt)
