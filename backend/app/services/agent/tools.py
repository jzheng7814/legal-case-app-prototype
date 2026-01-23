"""
Tools for the legal agent, adapting backend services.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Union
import re
import json
from pydantic import BaseModel, ValidationError

from app.services.documents import list_cached_documents, get_document
from app.services.checklists import get_checklist_definitions
# Note: we need access to the EvidenceCollection which is managed by the Driver/Ledger
# and eventually saved to ChecklistStore.

from app.services.agent.tokenizer import TokenizerWrapper


class BaseTool(ABC):
    """
    Abstract base class for all tools in the legal agent system.
    """
    
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.case_id: Optional[str] = None
        self.ledger: Any = None  # Will be injected
        self.tokenizer: Optional[TokenizerWrapper] = None
        self.store = None # Will be injected (ChecklistStore)

    def set_context(self, case_id: str, ledger: Any, tokenizer: TokenizerWrapper, store: Any):
        self.case_id = case_id
        self.ledger = ledger
        self.tokenizer = tokenizer
        self.store = store
    
    @abstractmethod
    def get_input_schema(self) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    def get_output_schema(self) -> Dict[str, Any]:
        pass
    
    def describe(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.get_input_schema(),
            "output_schema": self.get_output_schema()
        }
    
    def validate_args(self, args: Dict[str, Any]) -> Optional[str]:
        """
        Validates arguments against the schema.
        Returns error string if invalid, None if valid.
        """
        schema = self.get_input_schema()
        required = schema.get("required", [])
        properties = schema.get("properties", {})
        
        # Check required fields
        missing = [k for k in required if k not in args]
        if missing:
            return f"Missing required arguments: {', '.join(missing)}. Schema: {json.dumps(properties)}"
            
        # Check for unknown arguments (optional, but good for "hallucination" control)
        # unknown = [k for k in args if k not in properties]
        # if unknown:
        #    return f"Unknown arguments provided: {', '.join(unknown)}. Allowed: {list(properties.keys())}"
            
        return None

    def safe_call(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Wrapper that validates args before calling the tool.
        """
        error = self.validate_args(args)
        if error:
            return {"error": error}
        return self.call(args)

    @abstractmethod
    def call(self, args: Dict[str, Any]) -> Dict[str, Any]:
        pass
    

class ListDocumentsTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="list_documents",
            description="Returns all documents with their metadata (type, token_count). Use first if the catalog is unknown."
        )

    def get_input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": []
        }

    def get_output_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "documents": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "document_id": {"type": "integer"},
                            "title": {"type": "string"},
                            "type": {"type": "string"},
                            "token_count": {"type": "integer"}
                        }
                    }
                }
            }
        }

    def call(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if not self.case_id:
            return {"error": "Framework error: case_id not set in tool context"}
        
        try:
            docs = list_cached_documents(self.case_id)
            results = []
            for doc in docs:
                # Calculate tokens on the fly if not stored, defaulting to simple count if tokenizer fails
                # Using tokenizer from context
                text = doc.content or ""
                token_count = self.tokenizer.count_tokens(text) if self.tokenizer else len(text.split())
                
                results.append({
                    "document_id": doc.id,
                    "title": doc.title or f"Document {doc.id}",
                    "type": doc.type,
                    "token_count": token_count,
                    "description": doc.description
                })
            
            # Record discovery in ledger (if ledger exists)
            # In port: Ledger logic will be handled by Driver or here?
            # Start simpl: just return data.
            return {"documents": results}
        except Exception as e:
            return {"error": str(e)}


class ReadDocumentTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="read_document",
            description="Reads a specific token range from a document. start_token is inclusive; end_token is exclusive. Maximum range: 10,000 tokens per call."
        )

    def get_input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "doc_name": {"type": "string", "description": "Name or ID of the document to read"},
                "start_token": {"type": "integer"},
                "end_token": {"type": "integer"}
            },
            "required": ["doc_name", "start_token", "end_token"]
        }

    def get_output_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "doc_name": {"type": "string"},
                "start_token": {"type": "integer"},
                "end_token": {"type": "integer"},
                "error": {"type": "string"}
            }
        }

    def call(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if not self.case_id:
            return {"error": "Framework error: case_id not set"}
            
        doc_name = args.get("doc_name")
        start_token = args.get("start_token", 0)
        end_token = args.get("end_token", 0)
        
        # Resolve doc_name to ID
        # Simplification: Fetch all docs to find by title or ID
        # Optimization: documents service get_document expects ID, but we have helper for list.
        try:
            docs = list_cached_documents(self.case_id)
            target_doc = None
            
            # Try matching by exact ID if integer
            try:
                doc_id_int = int(doc_name)
                target_doc = next((d for d in docs if d.id == doc_id_int), None)
            except ValueError:
                pass # Not an integer ID
            
            if not target_doc:
                 # Match by title
                target_doc = next((d for d in docs if (d.title or "").strip() == str(doc_name).strip()), None)
            
            if not target_doc:
                # Fuzzy ID match "Document X"
                if str(doc_name).startswith("Document "):
                    try:
                        doc_id = int(str(doc_name).replace("Document ", ""))
                        target_doc = next((d for d in docs if d.id == doc_id), None)
                    except ValueError:
                        pass

            if not target_doc:
                return {"error": f"Document '{doc_name}' not found."}
            
            text = target_doc.content or ""
            
            # Tokenize and extract range
            # Re-tokenize might be slow for huge docs, ideally cache this in Ledger or DocumentManager
            if self.tokenizer:
                sub_text, actual_start, actual_end = self.tokenizer.get_text_for_token_range(text, start_token, end_token)
            else:
                # Fallback char/word slicing
                words = text.split()
                sub_text = " ".join(words[start_token:end_token])
                actual_start, actual_end = start_token, min(end_token, len(words))

            # Record read in ledger
            if self.ledger:
                self.ledger.record_read(target_doc.id, actual_start, actual_end)

            return {
                "text": sub_text,
                "doc_name": target_doc.title or f"Document {target_doc.id}",
                "start_token": actual_start,
                "end_token": actual_end,
                "total_tokens": self.tokenizer.count_tokens(text) if self.tokenizer else len(text.split())
            }

        except Exception as e:
            return {"error": str(e)}


class SearchDocumentRegexTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="search_document_regex",
            description="Searches documents using a regex pattern. Returns matches with ~context_tokens."
        )

    def get_input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "doc_name": {"type": "string", "description": "'all' or specific document name"},
                "context_tokens": {"type": "integer", "default": 200},
                "top_k": {"type": "integer", "default": 5}
            },
            "required": ["pattern"]
        }
    
    def get_output_schema(self) -> Dict[str, Any]:
        return {"type": "object"} # keeping simple

    def call(self, args: Dict[str, Any]) -> Dict[str, Any]:
        pattern = args.get("pattern")
        doc_name = args.get("doc_name", "all")
        context_tokens = args.get("context_tokens", 200)
        top_k = args.get("top_k", 5)
        
        try:
            regex = re.compile(pattern, re.IGNORECASE | re.MULTILINE)
        except re.error as e:
            return {"error": f"Invalid regex: {e}"}

        try:
            docs = list_cached_documents(self.case_id)
            targets = []
            if doc_name.lower() == "all":
                targets = docs
            else:
                # Same resolution logic as ReadDocument
                 # Try matching by exact ID if integer
                try:
                    doc_id_int = int(doc_name)
                    t = next((d for d in docs if d.id == doc_id_int), None)
                    if t: targets.append(t)
                except ValueError:
                    # Title matches
                    t = next((d for d in docs if (d.title or "") == doc_name), None)
                    if t: targets.append(t)
            
            if not targets:
                return {"error": f"No documents found for search target '{doc_name}'"}

            results = []
            
            for doc in targets:
                text = doc.content or ""
                matches = list(regex.finditer(text))
                
                doc_matches = []
                for m in matches[:top_k]:
                    start_char, end_char = m.span()
                    
                    # Get context window (approximation using characters if tokenizer slow, or tokenizer)
                    # For speed, let's use character approximation: 1 token ~ 4 chars
                    ctx_chars = context_tokens * 4
                    ctx_start = max(0, start_char - ctx_chars)
                    ctx_end = min(len(text), end_char + ctx_chars)
                    snippet = text[ctx_start:ctx_end]
                    
                    # Convert chars to estimated token positions for the agent
                    # This is rough but necessary.
                    # Or use tokenizer.token_to_char_positions reverse map? Too expensive.
                    # Just return text snippet.
                    doc_matches.append({
                        "match_text": m.group(),
                        "context": snippet,
                        "char_offset": start_char
                    })
                
                if doc_matches:
                    results.append({
                        "doc_name": doc.title or f"Document {doc.id}",
                        "matches": doc_matches
                    })
            
            return {"results": results}

        except Exception as e:
            return {"error": str(e)}


class GetChecklistTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="get_checklist",
            description="Retrieve extracted values for checklist items."
        )

    def get_input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "item": {"type": "string", "default": "all"},
                "items": {"type": "array", "items": {"type": "string"}}
            }
        }

    def get_output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    def call(self, args: Dict[str, Any]) -> Dict[str, Any]:
        # Access the EvidenceCollection via the injected Store/Ledger
        # The store maintains the current state of extraction
        if not self.store:
             return {"error": "Store not initialized"}
        
        current_state = self.store.get_current_collection() # Need to define this interface
        definitions = get_checklist_definitions()
        
        target_keys = set()
        items_arg = args.get("items", [])
        item_arg = args.get("item", "all")
        
        if items_arg:
            target_keys.update(items_arg)
        elif item_arg != "all":
            target_keys.add(item_arg)
        else:
            target_keys.update(definitions.keys())

        # Build response
        # Group by bin_id
        extracted = {}
        for item in current_state.items:
            if item.bin_id in target_keys:
                if item.bin_id not in extracted:
                    extracted[item.bin_id] = []
                extracted[item.bin_id].append({
                    "value": item.value,
                    "evidence": item.evidence.model_dump()
                })
        
        # Add empty keys
        for key in target_keys:
            if key not in extracted:
                extracted[key] = [] # Empty list implies not extracted yet
        
        return {"checklist": extracted}


class UpdateChecklistTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="update_checklist",
            description="REPLACES the entire extracted list for specified keys."
        )

    def get_input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "patch": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {"type": "string"},
                            "extracted": {"type": "array"} # items with evidence
                        },
                        "required": ["key", "extracted"]
                    }
                }
            },
            "required": ["patch"]
        }

    def get_output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    def call(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if not self.store:
            return {"error": "Store not initialized"}
        if not self.case_id:
             return {"error": "Framework error: case_id not set"}

        patches = args.get("patch", [])
        updated_keys = []
        errors = []
        
        # Helper to resolve doc IDs
        try:
             docs = list_cached_documents(self.case_id)
        except Exception:
             docs = []
             
        def resolve_doc_id(doc_name_or_id: Union[str, int]) -> int:
             # If already int or digit string
             if isinstance(doc_name_or_id, int):
                 return doc_name_or_id
             if str(doc_name_or_id).isdigit():
                 return int(doc_name_or_id)
             
             # Name match
             # Exact title match
             found = next((d for d in docs if (d.title or "") == str(doc_name_or_id)), None)
             if found: return int(found.id)
             
             # Fuzzy "Document X"
             if str(doc_name_or_id).startswith("Document "):
                 try:
                     return int(str(doc_name_or_id).replace("Document ", ""))
                 except:
                     pass
             
             # Fallback: maintain original logic (likely fail or let store handle)
             # But user wants strict INT. Return -1 or error?
             # Let's return -1 if not found, store will handle/warn.
             return -1

        for p in patches:
            key = p.get("key")
            items = p.get("extracted", [])
            
            # Resolve document IDs in evidence
            for item in items:
                evidence_list = item.get("evidence", [])
                if isinstance(evidence_list, dict):
                    evidence_list = [evidence_list]
                
                for ev in evidence_list:
                    raw_doc = ev.get("source_document")
                    if raw_doc is not None:
                        ev["source_document"] = resolve_doc_id(raw_doc)

            try:
                # Convert raw Dict items to EvidenceItem (or internal equivalent)
                # Validation logic here?
                self.store.update_key(key, items)
                updated_keys.append(key)
            except Exception as e:
                errors.append(f"Failed to update {key}: {e}")

        return {"updated_keys": updated_keys, "errors": errors}

class AppendChecklistTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="append_checklist",
            description="APPENDS new entries to existing extracted lists."
        )

    def get_input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                 "patch": {
                    "type": "array",
                    "items": {
                         "type": "object",
                         "properties": {
                            "key": {"type": "string"},
                            "extracted": {"type": "array"}
                         },
                         "required": ["key", "extracted"]
                    }
                 }
            },
            "required": ["patch"]
        }

    def get_output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    def call(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if not self.store:
            return {"error": "Store not initialized"}
        if not self.case_id:
             return {"error": "Framework error: case_id not set"}
            
        patches = args.get("patch", [])
        updated_keys = []
        errors = []
        
        # Helper to resolve doc IDs (Duplicated for now, could move to shared helper)
        try:
             docs = list_cached_documents(self.case_id)
        except Exception:
             docs = []
             
        def resolve_doc_id(doc_name_or_id: Union[str, int]) -> int:
             if isinstance(doc_name_or_id, int): return doc_name_or_id
             if str(doc_name_or_id).isdigit(): return int(doc_name_or_id)
             found = next((d for d in docs if (d.title or "") == str(doc_name_or_id)), None)
             if found: return int(found.id)
             if str(doc_name_or_id).startswith("Document "):
                 try:
                     return int(str(doc_name_or_id).replace("Document ", ""))
                 except:
                     pass
             return -1

        for p in patches:
            key = p.get("key")
            items = p.get("extracted", [])
            
            # Resolve document IDs in evidence
            for item in items:
                evidence_list = item.get("evidence", [])
                if isinstance(evidence_list, dict):
                    evidence_list = [evidence_list]
                
                for ev in evidence_list:
                    raw_doc = ev.get("source_document")
                    if raw_doc is not None:
                         ev["source_document"] = resolve_doc_id(raw_doc)

            try:
                self.store.append_to_key(key, items)
                updated_keys.append(key)
            except Exception as e:
                errors.append(f"Failed to append {key}: {e}")

        return {"updated_keys": updated_keys, "errors": errors}

