"""
Builds the Snapshot context from the agent state and documents.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime

from app.services.documents import list_cached_documents, Document
from app.services.agent.state import AgentChecklistStore, Ledger
from app.services.agent.schemas import (
    Snapshot, RunHeader, TaskInfo, ChecklistItem, ExtractedValue, 
    Evidence, DocumentInfo, DocumentCoverage, ActionRecord
)
from app.services.checklists import get_checklist_definitions

class SnapshotBuilder:
    def __init__(
        self,
        case_id: str,
        store: AgentChecklistStore,
        ledger: Ledger,
        tokenizer=None,
        checklist_config: Optional[Dict[str, Any]] = None,
        user_instruction: Optional[str] = None,
        task_constraints: Optional[List[str]] = None,
        recent_actions_detail: int = 3,
        max_action_tail: int = 100,
    ):
        self.case_id = case_id
        self.store = store
        self.ledger = ledger
        self.tokenizer = tokenizer
        self.checklist_config = checklist_config or {}
        self.user_instruction = user_instruction or "Extract all checklist items from the case corpus."
        self.task_constraints = task_constraints or []
        self.recent_actions_detail = recent_actions_detail
        self.max_action_tail = max_action_tail
        self._documents_discovered = False

    def mark_documents_discovered(self):
        self._documents_discovered = True

    def build(
        self,
        step: int,
        last_tool_result: Optional[Dict[str, Any]] = None,
        last_tool_name: Optional[str] = None,
        action_history: Optional[List[Dict[str, Any]]] = None,
        stop_count: int = 0,
        first_stop_step: Optional[int] = None,
    ) -> Snapshot:
        # 1. Available Documents (only after discovery)
        docs = list_cached_documents(self.case_id) if self._documents_discovered else []
        
        # Calculate coverage from ledger
        read_events = self.ledger.get_read_coverage() # List of {doc_id, start, end}
        doc_coverage_map = {}
        for event in read_events:
            did = event["doc_id"]
            if did not in doc_coverage_map:
                doc_coverage_map[did] = []
            doc_coverage_map[did].append([event["start"], event["end"]])
            
        document_infos = []
        for doc in docs:
            ranges = doc_coverage_map.get(doc.id, [])
            visited = len(ranges) > 0
            # Token count: ideal to have it cached. For now approximation if not in metadata.
            # In ListDocumentsTool we calc it. Here we might repeat work or just use len/4.
            # We'll rely on what's available or re-calc.
            text_len = len(doc.content or "")
            estimated_tokens = text_len // 4
            if self.tokenizer:
                estimated_tokens = self.tokenizer.count_tokens(doc.content or "")

            document_infos.append(DocumentInfo(
                id=doc.id,
                name=doc.title or f"Document {doc.id}",
                type=doc.type or "unknown",
                token_count=estimated_tokens,
                visited=visited,
                coverage=DocumentCoverage(token_ranges=ranges)
            ))

        # 2. Checklist State
        collection = self.store.get_current_collection()
        definitions = self.store.get_definitions() if hasattr(self.store, "get_definitions") else get_checklist_definitions()
        
        checklist_items = []
        # Group by key
        grouped_items = {}
        for item in collection.items:
            if item.bin_id not in grouped_items:
                grouped_items[item.bin_id] = []
            grouped_items[item.bin_id].append(item)
            
        all_keys = list(definitions.keys())
        for key in all_keys:
            items = grouped_items.get(key, [])
            extracted_values = []
            for it in items:
                ptr = it.evidence
                
                extracted_values.append(ExtractedValue(
                    value=it.value,
                    evidence=[Evidence(
                        text=ptr.text or "",
                        source_document=ptr.document_id,
                        location=ptr.location or "unknown"
                    )]
                ))
            
            checklist_items.append(ChecklistItem(
                key=key,
                description=definitions[key],
                extracted=extracted_values
            ))

        # 3. Action History
        action_records = []
        if action_history:
            recent_actions = action_history[-self.max_action_tail:] if len(action_history) > self.max_action_tail else action_history
            for action_data in recent_actions:
                action = action_data.get("action", {})
                tool_result = action_data.get("tool_result", {})
                action_records.append(ActionRecord(
                    step=action_data.get("step", 0),
                    tool=action.get("tool", "unknown"),
                    target=action.get("args"),
                    purpose=action.get("purpose"),
                    changed_keys=action_data.get("changed_keys"),
                    timestamp=action_data.get("timestamp"),
                    success=action_data.get("success", True),
                    error=action_data.get("error"),
                    validation_errors=action_data.get("validation_errors", []),
                    result_summary=tool_result if isinstance(tool_result, dict) else {"raw": str(tool_result)},
                    auto_generated=action_data.get("auto_generated", False),
                ))

        # 4. Recent Evidence Headers
        recent_evidence = []
        last_updated = self.store.get_last_updated() if hasattr(self.store, "get_last_updated") else {}
        sorted_keys = sorted(last_updated.keys(), key=lambda k: last_updated[k], reverse=True)
        evidence_count = 0
        for key in sorted_keys:
            if evidence_count >= 5:
                break
            items_for_key = [item for item in collection.items if item.bin_id == key]
            for item in items_for_key:
                if evidence_count >= 5:
                    break
                ptr = item.evidence
                recent_evidence.append(Evidence(
                    text=(ptr.text or "")[:100] + ("..." if ptr.text and len(ptr.text) > 100 else ""),
                    source_document=ptr.document_id,
                    location=ptr.location or "unknown",
                ))
                evidence_count += 1

        return Snapshot(
            run_header=RunHeader(step=step, case_id=self.case_id, timestamp=datetime.now()),
            task=TaskInfo(
                user_instruction=self.user_instruction,
                constraints=self.task_constraints,
                checklist_definitions=definitions
            ),
            checklist=checklist_items,
            documents=document_infos,
            action_tail=action_records,
            recent_evidence_headers=recent_evidence,
            last_tool_result=last_tool_result,
            last_tool_name=last_tool_name,
            recent_actions_detail=self.recent_actions_detail,
            stop_count=stop_count,
            first_stop_step=first_stop_step
        )
