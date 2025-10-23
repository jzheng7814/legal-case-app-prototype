from __future__ import annotations

import asyncio
import logging
import textwrap
import uuid
from typing import Dict

from fastapi import BackgroundTasks, HTTPException

from app.schemas.summary import SummaryJob, SummaryJobStatus, SummaryRequest
from app.services.documents import get_document
from app.services.llm import llm_service

logger = logging.getLogger(__name__)

_summary_jobs: Dict[str, SummaryJob] = {}
_summary_jobs_lock = asyncio.Lock()


async def create_summary_job(case_id: str, request: SummaryRequest, background_tasks: BackgroundTasks) -> SummaryJob:
    job_id = str(uuid.uuid4())
    job = SummaryJob(id=job_id, case_id=case_id, status=SummaryJobStatus.pending)
    async with _summary_jobs_lock:
        _summary_jobs[job_id] = job
    background_tasks.add_task(_run_summary_job, job_id, case_id, request)
    return job


async def _run_summary_job(job_id: str, case_id: str, request: SummaryRequest) -> None:
    await _update_job(job_id, status=SummaryJobStatus.running)

    try:
        compiled_context = []
        for document in request.documents:
            if document.include_full_text and document.content:
                title = document.title or document.alias or document.id
                compiled_context.append((document.id, title, document.content))
            else:
                doc = get_document(case_id, document.id)
                title = document.title or document.alias or doc.title or doc.id
                compiled_context.append((doc.id, title, doc.content))

        merged_corpus = "\n\n".join(
            f"Document {doc_id} — {doc_title}\n{textwrap.shorten(text, width=5000, placeholder=' …')}"
            for doc_id, doc_title, text in compiled_context
        )

        instruction_block = request.instructions or (
            "Produce a concise case summary highlighting parties, claims, procedural posture,"
            " key evidence, and damages. Do not use headers, bullet points, or lists. Write"
            " as if you were composing a short magazine article."
        )

        prompt = textwrap.dedent(
            f"""
            You are drafting a precise legal case summary for an attorney.\n
            Context documents:\n{merged_corpus}\n
            Instructions: {instruction_block}\n"""
        )

        summary_text = await llm_service.generate_text(prompt)
        await _update_job(job_id, status=SummaryJobStatus.succeeded, summary_text=summary_text.strip())
    except HTTPException:
        raise
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Failed to execute summary job %s", job_id)
        await _update_job(job_id, status=SummaryJobStatus.failed, error=str(exc))


async def _update_job(job_id: str, **updates) -> None:
    async with _summary_jobs_lock:
        job = _summary_jobs.get(job_id)
        if not job:
            return
        updated = job.model_copy(update=updates)
        _summary_jobs[job_id] = updated


async def get_summary_job(job_id: str) -> SummaryJob:
    async with _summary_jobs_lock:
        job = _summary_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Summary job not found")
    return job
