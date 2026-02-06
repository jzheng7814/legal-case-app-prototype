"""
State management for the agent (Checklist Store and Action Ledger).
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from pydantic import BaseModel

from app.eventing import get_event_producer
from app.schemas.checklists import EvidenceCollection, EvidenceItem, EvidencePointer
from app.services.checklists import get_checklist_definitions

class AgentChecklistStore:
    """
    In-memory store for the agent's extraction progress.
    """
    def __init__(self, checklist_config: Optional[Dict[str, Any]] = None):
        self._items: List[EvidenceItem] = []
        self._definitions = self._load_definitions(checklist_config)
        self._last_updated: Dict[str, datetime] = {}
        self._producer = get_event_producer(__name__)

    def _load_definitions(self, checklist_config: Optional[Dict[str, Any]]) -> Dict[str, str]:
        if checklist_config:
            return {
                key: (value.get("description") if isinstance(value, dict) else "")
                for key, value in checklist_config.items()
            }
        return get_checklist_definitions()
    
    def get_current_collection(self) -> EvidenceCollection:
        return EvidenceCollection(items=self._items)

    def get_definitions(self) -> Dict[str, str]:
        return dict(self._definitions)
    
    def update_key(self, key: str, items: List[Dict[str, Any]]):
        """
        Replace all items for a specific key (bin_id).
        """
        # Remove existing items for this key
        self._items = [i for i in self._items if i.bin_id != key]
        
        # Add new items
        for item_data in items:
            self._add_item(key, item_data)

        self._last_updated[key] = datetime.now()
        self._producer.debug(
            "Checklist updated",
            {"action": "update", "key": key, "items": items, "count": len(items)},
        )
            
    def append_to_key(self, key: str, items: List[Dict[str, Any]]):
        """
        Append items to a specific key.
        """
        for item_data in items:
            self._add_item(key, item_data)

        self._last_updated[key] = datetime.now()
        self._producer.debug(
            "Checklist updated",
            {"action": "append", "key": key, "items": items, "count": len(items)},
        )
            
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
            doc_id = ev.get("source_document")
            pointer = EvidencePointer(
                document_id=int(doc_id),
                location=ev.get("location"),
                text=ev.get("text"),
                start_offset=ev.get("start_offset"),
                end_offset=ev.get("end_offset"),
                verified=True,
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

    def get_empty_keys(self) -> List[str]:
        filled = set(i.bin_id for i in self._items)
        return [key for key in self._definitions.keys() if key not in filled]

    def get_last_updated(self) -> Dict[str, datetime]:
        return dict(self._last_updated)


class Ledger:
    """
    Log of agent actions.
    """
    def __init__(self):
        self.history: List[Dict[str, Any]] = []
        self.read_history: List[Dict[str, Any]] = [] # (doc_id, start, end)
        self.search_history: List[Dict[str, Any]] = []
        self._documents_discovered: bool = False

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

    def record_search(self, doc_ids: List[int], pattern: str):
        self.search_history.append({
            "doc_ids": doc_ids,
            "pattern": pattern
        })

    def mark_documents_discovered(self):
        self._documents_discovered = True

    def documents_discovered(self) -> bool:
        return self._documents_discovered

    def get_recent_history(self, n: int = 5) -> List[Dict[str, Any]]:
        return self.history[-n:]

    def get_read_coverage(self) -> List[Dict[str, Any]]:
        return self.read_history

    def get_visited_documents(self) -> List[int]:
        return list({entry["doc_id"] for entry in self.read_history})

    def get_document_coverage(self, doc_id: int) -> List[List[int]]:
        return [
            [entry["start"], entry["end"]]
            for entry in self.read_history
            if entry["doc_id"] == doc_id
        ]
