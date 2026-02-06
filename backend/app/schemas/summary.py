from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .documents import DocumentReference
from .checklists import EvidenceCategoryCollection


class SummaryJobStatus(str, Enum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class SummaryRequest(BaseModel):
    documents: List[DocumentReference] = Field(..., description="Documents that should inform the summary")
    checklist: EvidenceCategoryCollection = Field(..., description="Checklist items supplied by the client")
    instructions: Optional[str] = Field(
        None, description="Optional user guidance the LLM should follow when drafting the summary"
    )
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @model_validator(mode="after")
    def _validate_checklist(self) -> "SummaryRequest":
        doc_lookup = {int(doc.id): doc.content for doc in self.documents}
        for category in self.checklist.categories:
            for value in category.values:
                if value.document_id is None:
                    raise ValueError(
                        f"Checklist item {value.id} in category {category.id} is missing documentId."
                    )
                if value.start_offset is None or value.end_offset is None:
                    raise ValueError(
                        f"Checklist item {value.id} in category {category.id} is missing offsets."
                    )
                if value.start_offset >= value.end_offset:
                    raise ValueError(
                        f"Checklist item {value.id} in category {category.id} has invalid offsets."
                    )
                doc_text = doc_lookup.get(int(value.document_id))
                if doc_text is None:
                    raise ValueError(
                        f"Checklist item {value.id} in category {category.id} references missing document."
                    )
                if value.end_offset > len(doc_text):
                    raise ValueError(
                        f"Checklist item {value.id} in category {category.id} has offsets outside document bounds."
                    )
        return self


class SummaryJob(BaseModel):
    id: str
    case_id: str
    status: SummaryJobStatus
    summary_text: Optional[str] = None
    error: Optional[str] = None
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class SummaryJobEnvelope(BaseModel):
    job: SummaryJob
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
