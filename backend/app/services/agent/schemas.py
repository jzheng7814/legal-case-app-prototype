"""
Pydantic schemas for the agent state and snapshot.
"""

from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field

class Evidence(BaseModel):
    text: str
    source_document: str
    location: Optional[str] = None
    
class ExtractedValue(BaseModel):
    value: str
    evidence: List[Evidence] = Field(default_factory=list)

class ChecklistItem(BaseModel):
    key: str
    extracted: List[ExtractedValue] = Field(default_factory=list)
    description: Optional[str] = None

class DocumentCoverage(BaseModel):
    token_ranges: List[List[int]] = Field(default_factory=list) # List of [start, end]

class DocumentInfo(BaseModel):
    name: str
    type: str = "document"
    token_count: int = 0
    visited: bool = False
    coverage: Optional[DocumentCoverage] = None

class ActionRecord(BaseModel):
    step: int
    tool: str
    target: Optional[Dict[str, Any]] = None # Arguments
    result_summary: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    validation_errors: Optional[List[str]] = None
    auto_generated: bool = False
    changed_keys: Optional[List[str]] = None # Helper for display

class RunHeader(BaseModel):
    step: int
    case_id: str

class TaskInfo(BaseModel):
    user_instruction: str
    constraints: List[str] = Field(default_factory=list)
    checklist_definitions: Optional[Dict[str, str]] = None

class Snapshot(BaseModel):
    """
    Represents the full context window state for the agent.
    """
    run_header: RunHeader
    task: TaskInfo
    checklist: List[ChecklistItem]
    documents: List[DocumentInfo]
    action_tail: List[ActionRecord] = Field(default_factory=list)
    
    # Configuration/State flags
    recent_actions_detail: int = 5
    stop_count: int = 0
    first_stop_step: Optional[int] = None

class OrchestratorAction(BaseModel):
    """
    The structured decision output from the Orchestrator (LLM).
    """
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    stop_decision: bool = False
    stop_reason: Optional[str] = None
    thought: Optional[str] = None # Reasoning
