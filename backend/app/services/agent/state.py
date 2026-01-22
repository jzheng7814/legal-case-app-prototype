"""
State management for the agent (Checklist Store and Action Ledger).
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel

from app.schemas.checklists import EvidenceCollection, EvidenceItem, EvidencePointer
from app.services.checklists import get_checklist_definitions

class AgentChecklistStore:
    """
    In-memory store for the agent's extraction progress.
    """
    def __init__(self):
        self._items: List[EvidenceItem] = []
        self._definitions = get_checklist_definitions()
    
    def get_current_collection(self) -> EvidenceCollection:
        return EvidenceCollection(items=self._items)
    
    def update_key(self, key: str, items: List[Dict[str, Any]]):
        """
        Replace all items for a specific key (bin_id).
        """
        # Remove existing items for this key
        self._items = [i for i in self._items if i.bin_id != key]
        
        # Add new items
        for item_data in items:
            self._add_item(key, item_data)
            
    def append_to_key(self, key: str, items: List[Dict[str, Any]]):
        """
        Append items to a specific key.
        """
        for item_data in items:
            self._add_item(key, item_data)
            
    def _add_item(self, key: str, item_data: Dict[str, Any]):
        value = item_data.get("value")
        evidence_data = item_data.get("evidence")
        
        # specific handling for "multiple evidence" field coming from tool vs single evidence in schema
        # The schema in tools.py implies item_data has "evidence" which is list or object?
        # Tool definition: "extracted": [{"evidence": [...], "value": "..."}] (evidence is array in tool schema!)
        # Backend Schema: EvidenceItem has `evidence: EvidencePointer` (single).
        # We need to flatten if multiple evidence pieces support one value, OR duplicate the value item.
        # The sequential backend seems to support one pointer per item.
        # Decisions: Create multiple EvidenceItems if multiple evidence chunks provided for same value.
        
        evidence_list = evidence_data if isinstance(evidence_data, list) else [evidence_data]
        
        for ev in evidence_list:
            # Need to map tool evidence format to EvidencePointer
            # Tool: text, source_document, location
            # Pointer: document_id, start_offset, end_offset, text, verified
            
            # We assume the driver/tool logic has already resolved document names to IDs?
            # Actually UpdateChecklistTool passes raw dicts. We need to resolve them here or in Tool.
            # To keep Store simple, let's assume Tool passes semi-resolved data or we handle "text only" evidence.
            # But wait, EvidencePointer REQUIRES document_id (int).
            # The tool gets "source_document" which is a string (name).
            # Limitation: The Store needs to map doc name to ID if not already done.
            # Ideally, the Tool should resolve this since it has access to context/tokenizer.
            
            # Let's fix `tools.py` later to resolve doc IDs? 
            # OR, we make EvidencePointer optional in `EvidenceItem`? No, it's strict.
            # We'll assume for now `source_document` contains the ID or we can parse it.
            # But `tools.py` schema says "source_document" (string).
            
            # source_document should be an integer ID (resolved by Tool)
            # We strictly parse it as int.
            doc_id = -1
            src = ev.get("source_document")
            
            if isinstance(src, int):
                doc_id = src
            elif isinstance(src, str) and src.isdigit():
                doc_id = int(src)
            else:
                 # Fallback/Error state if tool failed to resolve
                 # We keep it as -1 which indicates "unknown document"
                 pass
            
            # Create object
            pointer = EvidencePointer(
                document_id=doc_id,
                text=ev.get("text"),
                start_offset=None, # Agent tools typically don't give exact offsets unless explicitly read
                end_offset=None,
                verified=True # Agent extracted
            )
            
            self._items.append(EvidenceItem(
                bin_id=key,
                value=value,
                evidence=pointer
            ))

    def get_completion_stats(self) -> Dict[str, int]:
        filled = set(i.bin_id for i in self._items)
        total = len(self._definitions)
        return {
            "filled": len(filled),
            "total": total,
            "empty": total - len(filled)
        }


class Ledger:
    """
    Log of agent actions.
    """
    def __init__(self):
        self.history: List[Dict[str, Any]] = []
        self.read_history: List[Dict[str, Any]] = [] # (doc_id, start, end)

    def record_action(self, step: int, tool_name: str, args: Dict, result: Any):
        self.history.append({
            "step": step,
            "tool": tool_name,
            "args": args,
            "result": result, # Can be large, maybe truncate for history?
            "timestamp": datetime.now().isoformat()
        })

    def record_read(self, doc_id: int, start: int, end: int):
        self.read_history.append({
            "doc_id": doc_id,
            "start": start,
            "end": end
        })

    def get_recent_history(self, n: int = 5) -> List[Dict[str, Any]]:
        return self.history[-n:]

    def get_read_coverage(self) -> List[Dict[str, Any]]:
        return self.read_history
