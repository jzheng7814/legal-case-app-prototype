import asyncio
from typing import Dict, Optional

from fastapi import APIRouter

from app.eventing import get_event_producer
from app.schemas.documents import DocumentListResponse, DocumentReference
from app.schemas.checklists import EvidenceCollection
from app.services.checklists import extract_document_checklists, get_document_checklists_if_cached
from app.services.documents import list_documents

router = APIRouter(prefix="/cases", tags=["cases"])
producer = get_event_producer(__name__)

_PREFETCH_TASKS: Dict[str, asyncio.Task] = {}
_PREFETCH_LOCK = asyncio.Lock()


@router.get("/{case_id}/documents", response_model=DocumentListResponse)
async def get_case_documents(case_id: str) -> DocumentListResponse:
    documents = list_documents(case_id)
    document_refs = [
        DocumentReference(
            id=doc.id,
            title=doc.title,
            include_full_text=True,
            content=doc.content,
            ecf_number=doc.ecf_number,
            date=doc.date,
            is_docket=doc.is_docket,
        )
        for doc in documents
    ]

    document_checklists: Optional[EvidenceCollection] = None
    checklist_status = "empty" if not document_refs else "pending"

    if document_refs:
        try:
            cached = await get_document_checklists_if_cached(case_id, document_refs)
        except Exception:  # pylint: disable=broad-except
            producer.error("Unable to inspect checklist cache", {"case_id": case_id})
            cached = None

        if cached is not None:
            document_checklists = cached
            checklist_status = "cached"
        else:
            await _schedule_prefetch(case_id, document_refs)

    return DocumentListResponse(
        case_id=case_id,
        documents=documents,
        document_checklists=document_checklists,
        checklist_status=checklist_status,
    )


async def _schedule_prefetch(case_id: str, references: list[DocumentReference]) -> None:
    async with _PREFETCH_LOCK:
        task = _PREFETCH_TASKS.get(case_id)
        if task is not None and not task.done():
            return
        cloned = [ref.model_copy(deep=True) for ref in references]
        _PREFETCH_TASKS[case_id] = asyncio.create_task(_prefetch_document_checklists(case_id, cloned))


async def _prefetch_document_checklists(case_id: str, references: list[DocumentReference]) -> None:
    try:
        await extract_document_checklists(case_id, references)
    except Exception:  # pylint: disable=broad-except
        producer.error("Checklist prefetch failed", {"case_id": case_id})
    finally:
        async with _PREFETCH_LOCK:
            tracked = _PREFETCH_TASKS.get(case_id)
            if tracked is asyncio.current_task() or tracked is None:
                _PREFETCH_TASKS.pop(case_id, None)
