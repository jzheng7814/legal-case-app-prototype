"""
Pydantic schemas for the agent state and snapshot.
"""

from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field

class Evidence(BaseModel):
    text: str
    source_document: int
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
    id: int
    name: str
    type: str = "document"
    token_count: int = 0
    visited: bool = False
    coverage: Optional[DocumentCoverage] = None

class ActionRecord(BaseModel):
    step: int
    tool: str
    target: Optional[Dict[str, Any]] = None
    purpose: Optional[str] = None
    changed_keys: Optional[List[str]] = None
    timestamp: Optional[Any] = None
    success: bool = True
    error: Optional[str] = None
    validation_errors: Optional[List[str]] = None
    result_summary: Optional[Dict[str, Any]] = None
    auto_generated: bool = False

class RunHeader(BaseModel):
    step: int
    case_id: str
    run_id: Optional[str] = None
    timestamp: Optional[Any] = None

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
    recent_evidence_headers: List[Evidence] = Field(default_factory=list)
    last_tool_result: Optional[Dict[str, Any]] = None
    last_tool_name: Optional[str] = None
    
    # Configuration/State flags
    recent_actions_detail: int = 5
    stop_count: int = 0
    first_stop_step: Optional[int] = None

class OrchestratorAction(BaseModel):
    """
    The structured decision output from the Orchestrator.
    Choose exactly ONE of:
    1. A 'tool_name' and 'tool_args' to execute a tool.
    2. 'stop_decision'=True and a 'stop_reason' to finish the task.
    """
    thought: str = Field(..., description="Brief reasoning for why this action was chosen.")
    
    # Tool Execution
    tool_name: Optional[str] = Field(None, description="Name of the tool to execute. Required unless stopping.")
    tool_args: Optional[Dict[str, Any]] = Field(None, description="Arguments for the tool. Required unless stopping.")
    
    # Stop condition
    stop_decision: bool = Field(False, description="Set to True ONLY if all checklist items are extracted or no further actions are possible.")
    stop_reason: Optional[str] = Field(None, description="Explanation for why the agent is stopping. Required if stop_decision is True.")
