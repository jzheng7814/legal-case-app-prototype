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
from app.services.checklists import get_checklist_definitions, get_checklist_definitions

class SnapshotBuilder:
    def __init__(self, 
                 case_id: str, 
                 store: AgentChecklistStore, 
                 ledger: Ledger,
                 tokenizer = None): # Tokenizer optional if needed for count
        self.case_id = case_id
        self.store = store
        self.ledger = ledger
        self.tokenizer = tokenizer

    def build(self, step: int) -> Snapshot:
        # 1. Available Documents
        docs = list_cached_documents(self.case_id)
        
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
                 name=doc.title or f"Document {doc.id}",
                 type=doc.type or "unknown",
                 token_count=estimated_tokens,
                 visited=visited,
                 coverage=DocumentCoverage(token_ranges=ranges)
             ))

        # 2. Checklist State
        collection = self.store.get_current_collection()
        definitions = get_checklist_definitions()
        
        checklist_items = []
        # Group by key
        grouped_items = {}
        for item in collection.items:
            if item.bin_id not in grouped_items:
                grouped_items[item.bin_id] = []
            grouped_items[item.bin_id].append(item)
            
        all_keys = sorted(definitions.keys())
        for key in all_keys:
            items = grouped_items.get(key, [])
            extracted_values = []
            for it in items:
                # Convert EvidencePointer back to our Schema Evidence
                # We need doc name. Pointer has ID.
                # We need to map ID -> Name.
                # Inefficient: find doc by ID.
                doc_name = "unknown"
                ptr = it.evidence
                found_doc = next((d for d in docs if d.id == ptr.document_id), None)
                if found_doc:
                    doc_name = found_doc.title or f"Document {found_doc.id}"
                
                extracted_values.append(ExtractedValue(
                    value=it.value,
                    evidence=[Evidence(
                        text=ptr.text or "",
                        source_document=doc_name,
                        location=f"offset {ptr.start_offset}" if ptr.start_offset else "unknown"
                    )]
                ))
            
            checklist_items.append(ChecklistItem(
                key=key,
                description=definitions[key],
                extracted=extracted_values
            ))

        # 3. Action History
        recent_history = self.ledger.get_recent_history(10) # Get last 10
        action_records = []
        for h in recent_history:
            action_records.append(ActionRecord(
                step=h["step"],
                tool=h["tool"],
                target=h["args"],
                result_summary=h["result"] if isinstance(h["result"], dict) else {"raw": str(h["result"])},
                # error/validation not tracked in simplified ledger yet, need to add
            ))

        return Snapshot(
            run_header=RunHeader(step=step, case_id=self.case_id),
            task=TaskInfo(
                user_instruction="Extract the items for the legal case.",
                checklist_definitions=definitions
            ),
            checklist=checklist_items,
            documents=document_infos,
            action_tail=action_records,
            recent_actions_detail=5
        )
