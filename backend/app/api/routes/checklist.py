from typing import List

from fastapi import APIRouter

from app.schemas.checklists import ChecklistCategoryCollection, ChecklistItemCreateRequest
from app.schemas.documents import DocumentReference
from app.services import checklists as checklist_service
from app.services.documents import list_documents

router = APIRouter(prefix="/cases", tags=["checklists"])


def _build_document_references(case_id: str) -> List[DocumentReference]:
    documents = list_documents(case_id)
    return [
        DocumentReference(
            id=doc.id,
            title=doc.title,
            include_full_text=True,
            content=doc.content,
        )
        for doc in documents
    ]


@router.get("/{case_id}/checklist", response_model=ChecklistCategoryCollection)
async def get_case_checklist(case_id: str) -> ChecklistCategoryCollection:
    document_refs = _build_document_references(case_id)
    record = await checklist_service.ensure_document_checklist_record(case_id, document_refs)
    return checklist_service.build_category_collection(record)


@router.post("/{case_id}/checklist/items", response_model=ChecklistCategoryCollection)
async def add_checklist_item(case_id: str, payload: ChecklistItemCreateRequest) -> ChecklistCategoryCollection:
    document_refs = _build_document_references(case_id)
    record = await checklist_service.ensure_document_checklist_record(case_id, document_refs)
    updated = checklist_service.append_user_checklist_value(case_id, record, payload)
    return checklist_service.build_category_collection(updated)


@router.delete("/{case_id}/checklist/items/{value_id}", response_model=ChecklistCategoryCollection)
async def delete_checklist_item(case_id: str, value_id: str) -> ChecklistCategoryCollection:
    updated = await checklist_service.remove_checklist_value(case_id, value_id)
    return checklist_service.build_category_collection(updated)
