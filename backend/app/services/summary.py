from __future__ import annotations

import asyncio
import logging
import uuid
import textwrap
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

STYLE_ONE_SHOT = textwrap.dedent(
    """
    This case challenges the University of Virginia (UVA) and affiliated campus groups for allegedly permitting and failing to prevent pervasive antisemitism on its campus, particularly after the October 7 attacks, in violation of federal and state law. Other cases involving universities' responses to speech and activity concerning Israel and Palestine, including matters of antisemitism or anti-Palestinian expression, can be found here.

    On May 17, 2024, an Israeli-American student at UVA filed suit in the U.S. District Court for the Western District of Virginia. The complaint named UVA, its President (Ryan), its Rector (Hardie), and two campus groups, the Faculty for Justice in Palestine (FJP) and Students for Justice in Palestine (SJP). The plaintiff asserted Title VI claims against UVA; claims under 42 U.S.C. Sections 1981, 1983, and 1988 against President Ryan and Rector Hardie; and claims against FJP and SJP under Virginia Code Section 8.01-42.1, 42 U.S.C. Sections 1981 and 1988, as well as common-law claims for negligence, gross negligence, and intentional infliction of emotional distress. He sought declaratory and injunctive relief, damages, and attorneys' fees. The case was assigned to Judge Robert S. Ballou.

    In the complaint, the plaintiff alleged that, as a result of the defendants' conduct, he was subjected to discrimination, harassment, and retaliation because of his Jewish and Israeli identity. He alleged that UVA and its officials created a hostile educational environment, denied him equal access to programs, and targeted him for protected activity. He further claimed that FJP and SJP members engaged in harassment and intimidation, causing him emotional distress.

    Defendants FJP and SJP filed a joint motion to dismiss on July 1, 2024, arguing that their actions were protected by the First Amendment, that the plaintiff lacked standing, and that the complaint failed to state statutory or tort claims. Defendants UVA, Rector Hardie, and President Ryan filed a separate motion asserting that the plaintiff lacked standing, failed to allege intentional discrimination or retaliation, raised insufficient hostile-environment claims, and that claims against Ryan and Hardie were barred by the Eleventh Amendment and qualified immunity.

    On August 6, 2024, the plaintiff voluntarily dismissed the claims against defendant Rector Hardie without prejudice.

    That same day, the plaintiff filed an amended complaint that, among other changes, removed Rector Hardie from the action, expanded the existing federal civil rights claim against FJP and SJP to include alleged violations of 42 U.S.C. Sections 1985 and 1986, and added a new civil conspiracy claim against FJP and SJP. On September 10, 2024, defendants UVA and President Ryan filed a motion to dismiss the amended complaint, arguing that the plaintiff failed to allege intentional discrimination, retaliation, or a viable hostile environment claim under Title VI, and that all claims against President Ryan are unsupported and barred by qualified immunity.

    The plaintiff voluntarily dismissed the claims against defendants SJP and FJP without prejudice on September 16, 2024. The next day, the court entered an order dismissing the case without prejudice as to these student groups.

    On November 19, 2024, the plaintiff and defendants UVA and President Ryan entered into a stipulation of dismissal with prejudice. On December 4, 2024, the court ordered the action dismissed with prejudice as to these parties.

    Although the reason for the various dismissals has not been made public, The Cavalier Daily reported that the case ended in a settlement that was not disclosed to the public.

    This case is closed.
    """
)


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
            "Produce a clear, formal case narrative written for an educated general audience. "
            "Keep the tone professional but avoid legalese and unnecessary jargon. "
            "Follow the chronological flow of the evidence. "
            "Write in straightforward, objective prose at approximately an 11th-12th grade reading level. "
            "Do not use headers, numbered sections, bullet points, lists, or first/second person. "
            "Open with the dispute frame in one sentence; then procedural posture; then factual allegations; then motions/resolutions; close with disposition/status."
        )

        style_guidance = (
            "Style example (cadence only; do not treat this as evidence):\n"
            f"{STYLE_ONE_SHOT.strip()}\n"
            "Use only the provided evidence above for facts; do not borrow facts, dates, parties, or claims from the style example."
        )

        prompt = (
            "You are drafting a precise legal case summary for an attorney.\n"
            "Use the evidence below in the order presented (document order, then position within document) and maintain"
            " a clear sense of the case state as it evolves.\n\n"
            f"Evidence (chronological):\n{evidence_block}\n\n"
            f"Instructions:\n{instruction_block}\n\n"
            f"{style_guidance}\n"
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
            evidence_text = evidence_text[:400] + " ..."
        snippet = f' "{evidence_text}"' if evidence_text else ""
        offset_part = ""
        if item.evidence.start_offset is not None and item.evidence.end_offset is not None:
            offset_part = f" offsets [{item.evidence.start_offset}-{item.evidence.end_offset}]"
        lines.append(f"- Doc {doc_id} - {title}: [{item.bin_id}] {item.value}{offset_part}{snippet}")
    return "\n".join(lines)
