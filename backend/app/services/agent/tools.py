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


def _validate_patch_payload(patches: Any) -> List[str]:
    errors: List[str] = []
    if not isinstance(patches, list) or not patches:
        return ["Patch must be a non-empty array."]

    for idx, patch in enumerate(patches):
        if not isinstance(patch, dict):
            errors.append(f"Patch {idx} must be an object.")
            continue
        key = patch.get("key")
        if not isinstance(key, str) or not key.strip():
            errors.append(f"Patch {idx} missing valid key.")
        extracted = patch.get("extracted")
        if not isinstance(extracted, list) or not extracted:
            errors.append(f"Patch {idx} must include a non-empty extracted list.")
            continue
        for eidx, entry in enumerate(extracted):
            if not isinstance(entry, dict):
                errors.append(f"Patch {idx} extracted[{eidx}] must be an object.")
                continue
            value = entry.get("value")
            if not isinstance(value, str):
                errors.append(f"Patch {idx} extracted[{eidx}] missing string value.")
            evidence_list = entry.get("evidence")
            if not isinstance(evidence_list, list) or not evidence_list:
                errors.append(f"Patch {idx} extracted[{eidx}] must include non-empty evidence list.")
                continue
            for vidx, ev in enumerate(evidence_list):
                if not isinstance(ev, dict):
                    errors.append(f"Patch {idx} extracted[{eidx}] evidence[{vidx}] must be an object.")
                    continue
                text = ev.get("text")
                source_document = ev.get("source_document")
                location = ev.get("location")
                if not isinstance(text, str) or not text.strip():
                    errors.append(f"Patch {idx} extracted[{eidx}] evidence[{vidx}] missing text.")
                if not isinstance(source_document, int) or source_document < 0:
                    errors.append(f"Patch {idx} extracted[{eidx}] evidence[{vidx}] source_document must be a non-negative int.")
                if not isinstance(location, str) or not location.strip():
                    errors.append(f"Patch {idx} extracted[{eidx}] evidence[{vidx}] missing location.")

    return errors


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
                            "token_count": {"type": "integer"},
                            "visited": {"type": "boolean"},
                            "coverage": {
                                "type": "object",
                                "properties": {
                                    "token_ranges": {
                                        "type": "array",
                                        "items": {
                                            "type": "array",
                                            "items": {"type": "integer"}
                                        }
                                    }
                                }
                            }
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
                visited = False
                coverage = []
                if self.ledger:
                    visited = doc.id in self.ledger.get_visited_documents()
                    coverage = self.ledger.get_document_coverage(doc.id)
                
                results.append({
                    "document_id": doc.id,
                    "title": doc.title or f"Document {doc.id}",
                    "type": doc.type,
                    "token_count": token_count,
                    "visited": visited,
                    "coverage": {"token_ranges": coverage},
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
                "doc_id": {"type": "integer", "description": "ID of the document to read"},
                "start_token": {"type": "integer"},
                "end_token": {"type": "integer"}
            },
            "required": ["doc_id", "start_token", "end_token"]
        }

    def get_output_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "doc_id": {"type": "integer"},
                "start_token": {"type": "integer"},
                "end_token": {"type": "integer"},
                "error": {"type": "string"}
            }
        }

    def call(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if not self.case_id:
            return {"error": "Framework error: case_id not set"}

        doc_id = args.get("doc_id")
        start_token = args.get("start_token", 0)
        end_token = args.get("end_token", 0)

        try:
            docs = list_cached_documents(self.case_id)
            target_doc = next((d for d in docs if d.id == doc_id), None)
            if not target_doc:
                return {"error": f"Document id '{doc_id}' not found."}

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
                "doc_id": target_doc.id,
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
                "doc_id": {"type": "integer", "description": "Single document ID or -1 for all documents"},
                "doc_ids": {"type": "array", "items": {"type": "integer"}, "description": "Array of document IDs to search"},
                "flags": {"type": "array", "items": {"type": "string"}, "default": []},
                "context_tokens": {"type": "integer", "default": 200},
                "top_k": {"type": "integer", "default": 5}
            },
            "required": ["pattern"]
        }
    
    def get_output_schema(self) -> Dict[str, Any]:
        return {"type": "object"} # keeping simple

    def call(self, args: Dict[str, Any]) -> Dict[str, Any]:
        pattern = args.get("pattern")
        doc_id = args.get("doc_id")
        doc_ids = args.get("doc_ids") or []
        flags = args.get("flags", [])
        context_tokens = args.get("context_tokens", 200)
        top_k = args.get("top_k", 5)
        
        try:
            regex_flags = 0
            for flag in flags:
                if flag == "IGNORECASE":
                    regex_flags |= re.IGNORECASE
                elif flag == "MULTILINE":
                    regex_flags |= re.MULTILINE
                elif flag == "DOTALL":
                    regex_flags |= re.DOTALL
            regex = re.compile(pattern, regex_flags)
        except re.error as e:
            return {"error": f"Invalid regex: {e}"}

        try:
            docs = list_cached_documents(self.case_id)
            targets = []
            if doc_ids:
                targets = [d for d in docs if d.id in doc_ids]
            elif doc_id == -1:
                targets = docs
            elif doc_id is not None:
                targets = [d for d in docs if d.id == doc_id]
            else:
                return {"error": "doc_id or doc_ids is required (use doc_id=-1 for all documents)."}

            if not targets:
                return {"error": "No documents found for the requested search target(s)."}

            results = []
            total_matches = 0
            documents_searched = []
            
            for doc in targets:
                text = doc.content or ""
                matches = list(regex.finditer(text))
                documents_searched.append(doc.id)

                doc_matches = []
                for m in matches[:top_k]:
                    start_char, end_char = m.span()
                    if self.tokenizer:
                        tokens = self.tokenizer.encode(text)
                        approx_token = int((start_char / max(len(text), 1)) * len(tokens)) if tokens else 0
                        context_start = max(0, approx_token - context_tokens // 2)
                        context_end = min(len(tokens), approx_token + context_tokens // 2)
                        snippet, _, _ = self.tokenizer.get_text_for_token_range(text, context_start, context_end)
                        start_token = context_start
                        end_token = context_end
                    else:
                        ctx_chars = context_tokens * 4
                        ctx_start = max(0, start_char - ctx_chars)
                        ctx_end = min(len(text), end_char + ctx_chars)
                        snippet = text[ctx_start:ctx_end]
                        start_token = 0
                        end_token = 0

                    doc_matches.append({
                        "start_token": start_token,
                        "end_token": end_token,
                        "start_char": start_char,
                        "end_char": end_char,
                        "snippet": snippet,
                        "groups": m.groupdict(),
                        "pattern": pattern,
                        "flags": flags
                    })
                
                if doc_matches:
                    total_matches += len(doc_matches)
                    results.append({
                        "doc_id": doc.id,
                        "match_count": len(doc_matches),
                        "matches": doc_matches
                    })

            if self.ledger:
                self.ledger.record_search([d.id for d in targets], pattern)

            return {
                "pattern": pattern,
                "documents_searched": documents_searched,
                "results": results,
                "total_matches": total_matches
            }

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

        completion_stats = self.store.get_completion_stats() if hasattr(self.store, "get_completion_stats") else {}
        return {"checklist": extracted, "completion_stats": completion_stats}


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
                            "extracted": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "evidence": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "text": {"type": "string"},
                                                    "source_document": {"type": "integer"},
                                                    "location": {"type": "string"},
                                                },
                                                "required": ["text", "source_document", "location"],
                                            },
                                        },
                                        "value": {"type": "string"},
                                    },
                                    "required": ["evidence", "value"],
                                },
                            },
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

        validation_errors = _validate_patch_payload(patches)
        if validation_errors:
            return {"updated_keys": [], "validation_errors": validation_errors, "success": False}

        for p in patches:
            key = p.get("key")
            items = p.get("extracted", [])
            try:
                self.store.update_key(key, items)
                updated_keys.append(key)
            except Exception as e:
                errors.append(f"Failed to update {key}: {e}")

        success = len(errors) == 0
        if not success:
            return {"updated_keys": updated_keys, "validation_errors": errors, "success": False}

        return {"updated_keys": updated_keys, "validation_errors": [], "success": True}

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
                            "extracted": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "evidence": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "text": {"type": "string"},
                                                    "source_document": {"type": "integer"},
                                                    "location": {"type": "string"},
                                                },
                                                "required": ["text", "source_document", "location"],
                                            },
                                        },
                                        "value": {"type": "string"},
                                    },
                                    "required": ["evidence", "value"],
                                },
                            }
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

        validation_errors = _validate_patch_payload(patches)
        if validation_errors:
            return {"updated_keys": [], "validation_errors": validation_errors, "success": False}

        for p in patches:
            key = p.get("key")
            items = p.get("extracted", [])
            try:
                self.store.append_to_key(key, items)
                updated_keys.append(key)
            except Exception as e:
                errors.append(f"Failed to append {key}: {e}")

        success = len(errors) == 0
        if not success:
            return {"updated_keys": updated_keys, "validation_errors": errors, "success": False}

        return {"updated_keys": updated_keys, "validation_errors": [], "success": True}


from pydantic import Field

class StopTool(BaseTool):
    """
    Tool for the agent to signal that it wants to stop the task.
    """
    def __init__(self):
        super().__init__(
            name="stop_task",
            description="Stop the extraction task. CALL THIS ONLY when you have extracted all information or cannot proceed further. You must provide a reason."
        )

    def get_input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string", 
                    "description": "Explanation for why the agent is stopping."
                }
            },
            "required": ["reason"]
        }

    def get_output_schema(self) -> Dict[str, Any]:
        return {"type": "object"}

    def call(self, args: Dict[str, Any]) -> Dict[str, Any]:
        # The Orchestrator handles the actual stopping logic based on this tool call being present.
        # This function just returns the reason to confirm.
        return {"status": "stopping", "reason": args.get("reason", "No reason provided")}
