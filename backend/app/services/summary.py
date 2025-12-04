from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Dict, List, Optional

from fastapi import BackgroundTasks, HTTPException

from app.schemas.checklists import EvidenceCollection, EvidenceItem
from app.schemas.documents import DocumentReference
from app.schemas.summary import SummaryJob, SummaryJobStatus, SummaryRequest
from app.services.checklists import extract_document_checklists
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
        sorted_docs = sorted(request.documents, key=_document_sort_key)
        evidence = await extract_document_checklists(case_id, sorted_docs)
        doc_titles = _build_document_titles(case_id, sorted_docs)
        ordered_items = _order_evidence_items(evidence, doc_titles)
        evidence_block = _format_evidence_block(ordered_items, doc_titles)

        instruction_block = request.instructions or (
            "Produce a concise, formal legal narrative highlighting parties, claims, procedural posture, key evidence, and outcomes."
            " Follow the chronological flow of the evidence. Do not use headers, numbered sections, bullet points, or lists."
            " Write in clear, objective prose with short paragraphs separated by line breaks; avoid colloquialisms and first/second person."
        )

        prompt = (
            "You are drafting a precise legal case summary for an attorney.\n"
            "Use the evidence below in the order presented (document order, then position within document) and maintain"
            " a clear sense of the case state as it evolves.\n\n"
            f"Evidence (chronological):\n{evidence_block}\n\n"
            f"Instructions: {instruction_block}\n"
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


def _parse_ecf_key(raw_value: Optional[str]) -> tuple[int, int, object]:
    if raw_value is None:
        return (1, 1, "")
    text = str(raw_value).strip()
    if not text:
        return (1, 1, "")
    try:
        number = int(text)
        return (0, 0, number)
    except (TypeError, ValueError):
        return (0, 1, text)


def _document_sort_key(document: DocumentReference) -> tuple:
    ecf_flags = _parse_ecf_key(getattr(document, "ecf_number", None))
    return (
        0 if getattr(document, "is_docket", False) else 1,
        ecf_flags[0],
        ecf_flags[1],
        ecf_flags[2],
        document.id,
    )


def _build_document_titles(case_id: str, documents: List[DocumentReference]) -> Dict[int, str]:
    titles: Dict[int, str] = {}
    for ref in documents:
        display_title = ref.title or ref.alias
        if display_title is None:
            try:
                doc = get_document(case_id, ref.id)
                display_title = doc.title or doc.id
            except Exception:  # pylint: disable=broad-except
                display_title = ref.id
        titles[int(ref.id)] = str(display_title)
    return titles


def _order_evidence_items(evidence: EvidenceCollection, titles: Dict[int, str]) -> List[EvidenceItem]:
    doc_order = {doc_id: idx for idx, doc_id in enumerate(titles.keys())}
    return sorted(
        evidence.items,
        key=lambda item: (
            doc_order.get(item.evidence.document_id, len(doc_order)),
            item.evidence.start_offset if item.evidence.start_offset is not None else 0,
        ),
    )


def _format_evidence_block(items: List[EvidenceItem], titles: Dict[int, str]) -> str:
    lines: List[str] = []
    for item in items:
        doc_id = item.evidence.document_id
        title = titles.get(doc_id, f"Document {doc_id}")
        evidence_text = item.evidence.text or ""
        evidence_text = evidence_text.replace("\n", " ").strip()
        if len(evidence_text) > 400:
            evidence_text = evidence_text[:400] + " …"
        snippet = f' "{evidence_text}"' if evidence_text else ""
        offset_part = ""
        if item.evidence.start_offset is not None and item.evidence.end_offset is not None:
            offset_part = f" offsets [{item.evidence.start_offset}-{item.evidence.end_offset}]"
        lines.append(f"- Doc {doc_id} — {title}: [{item.bin_id}] {item.value}{offset_part}{snippet}")
    return "\n".join(lines)
