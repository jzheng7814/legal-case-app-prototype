from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .documents import DocumentReference


class SummaryJobStatus(str, Enum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class SummaryRequest(BaseModel):
    documents: List[DocumentReference] = Field(..., description="Documents that should inform the summary")
    instructions: Optional[str] = Field(
        None, description="Optional user guidance the LLM should follow when drafting the summary"
    )
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


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
