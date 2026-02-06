"""
Tools for the legal agent, adapting backend services.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Union, Tuple
import re
import json
from pydantic import BaseModel, ValidationError

from app.services.documents import list_cached_documents, get_document
from app.services.checklists import get_checklist_definitions
# Note: we need access to the EvidenceCollection which is managed by the Driver/Ledger
# and eventually saved to ChecklistStore.

from app.services.agent.tokenizer import TokenizerWrapper
from app.services.agent.sentences import build_sentence_index


MAX_SENTENCES_PER_READ = 200


def _extract_document_id(ev: Dict[str, Any]) -> Optional[int]:
    for key in ("document_id", "documentId", "source_document", "sourceDocument", "doc_id"):
        value = ev.get(key)
        if isinstance(value, int):
            return value
    return None


def _extract_sentence_ids(ev: Dict[str, Any]) -> Optional[List[int]]:
    for key in ("sentence_ids", "sentenceIds"):
        value = ev.get(key)
        if isinstance(value, list):
            if not all(isinstance(entry, int) for entry in value):
                return None
            return value
    return None


def _validate_contiguous_sentence_ids(sentence_ids: List[int]) -> Optional[str]:
    if not sentence_ids:
        return "sentence_ids must be a non-empty list."
    ordered = sorted(sentence_ids)
    for prev, nxt in zip(ordered, ordered[1:]):
        if nxt != prev + 1:
            return "sentence_ids must be contiguous."
    return None


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
                doc_id = _extract_document_id(ev)
                if doc_id is None or doc_id < 0:
                    errors.append(
                        f"Patch {idx} extracted[{eidx}] evidence[{vidx}] document_id must be a non-negative int."
                    )
                sentence_ids = _extract_sentence_ids(ev)
                if sentence_ids is None:
                    errors.append(
                        f"Patch {idx} extracted[{eidx}] evidence[{vidx}] sentence_ids must be a list of integers."
                    )
                else:
                    contiguous_error = _validate_contiguous_sentence_ids(sentence_ids)
                    if contiguous_error:
                        errors.append(
                            f"Patch {idx} extracted[{eidx}] evidence[{vidx}] {contiguous_error}"
                        )

    return errors


def _normalize_sentence_text(text: str) -> str:
    return " ".join(text.split())


def _resolve_sentence_evidence(case_id: str, ev: Dict[str, Any]) -> Dict[str, Any]:
    doc_id = _extract_document_id(ev)
    if doc_id is None:
        raise ValueError("Evidence missing document_id.")

    sentence_ids = _extract_sentence_ids(ev)
    if sentence_ids is None:
        raise ValueError("Evidence missing sentence_ids.")

    contiguous_error = _validate_contiguous_sentence_ids(sentence_ids)
    if contiguous_error:
        raise ValueError(contiguous_error)

    docs = list_cached_documents(case_id)
    target_doc = next((d for d in docs if d.id == doc_id), None)
    if not target_doc:
        raise ValueError(f"Document id '{doc_id}' not found.")

    text = target_doc.content or ""
    spans = build_sentence_index(case_id, doc_id, text)
    if not spans:
        raise ValueError("No sentences found in document.")

    start_id = min(sentence_ids)
    end_id = max(sentence_ids)
    if start_id < 0 or end_id >= len(spans):
        raise ValueError("sentence_ids out of range for document.")

    start_char = spans[start_id].start_char
    end_char = spans[end_id].end_char
    snippet = text[start_char:end_char]
    location = f"sentences {start_id}-{end_id}" if start_id != end_id else f"sentence {start_id}"

    return {
        "source_document": doc_id,
        "start_offset": start_char,
        "end_offset": end_char,
        "text": snippet,
        "location": location,
    }


def _find_sentence_id(spans: List["SentenceSpan"], char_pos: int) -> Optional[int]:
    # Simple binary search over span starts.
    left = 0
    right = len(spans) - 1
    while left <= right:
        mid = (left + right) // 2
        span = spans[mid]
        if char_pos < span.start_char:
            right = mid - 1
        elif char_pos >= span.end_char:
            left = mid + 1
        else:
            return span.sentence_id
    return None


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
            description="Returns all documents with their metadata (type, sentence_count). Use first if the catalog is unknown."
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
                            "sentence_count": {"type": "integer"},
                            "visited": {"type": "boolean"},
                            "coverage": {
                                "type": "object",
                                "properties": {
                                    "sentence_ranges": {
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
                text = doc.content or ""
                sentence_count = len(build_sentence_index(self.case_id, doc.id, text))
                visited = False
                coverage = []
                if self.ledger:
                    visited = doc.id in self.ledger.get_visited_documents()
                    coverage = self.ledger.get_document_coverage(doc.id)
                
                results.append({
                    "document_id": doc.id,
                    "title": doc.title or f"Document {doc.id}",
                    "type": doc.type,
                    "sentence_count": sentence_count,
                    "visited": visited,
                    "coverage": {"sentence_ranges": coverage},
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
            description="Reads a specific sentence range from a document. start_sentence is inclusive; end_sentence is exclusive. Maximum range: 200 sentences per call."
        )

    def get_input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "doc_id": {"type": "integer", "description": "ID of the document to read"},
                "start_sentence": {"type": "integer"},
                "end_sentence": {"type": "integer"}
            },
            "required": ["doc_id", "start_sentence", "end_sentence"]
        }

    def get_output_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "doc_id": {"type": "integer"},
                "start_sentence": {"type": "integer"},
                "end_sentence": {"type": "integer"},
                "total_sentences": {"type": "integer"},
                "error": {"type": "string"}
            }
        }

    def call(self, args: Dict[str, Any]) -> Dict[str, Any]:
        if not self.case_id:
            return {"error": "Framework error: case_id not set"}

        doc_id = args.get("doc_id")
        start_sentence = args.get("start_sentence", 0)
        end_sentence = args.get("end_sentence", 0)

        try:
            docs = list_cached_documents(self.case_id)
            target_doc = next((d for d in docs if d.id == doc_id), None)
            if not target_doc:
                return {"error": f"Document id '{doc_id}' not found."}

            text = target_doc.content or ""
            spans = build_sentence_index(self.case_id, target_doc.id, text)
            total_sentences = len(spans)
            if total_sentences == 0:
                return {"error": "Document has no sentences."}

            if end_sentence <= start_sentence:
                return {"error": "end_sentence must be greater than start_sentence."}

            start_sentence = max(0, min(start_sentence, total_sentences))
            end_sentence = max(start_sentence, min(end_sentence, total_sentences))

            if end_sentence - start_sentence > MAX_SENTENCES_PER_READ:
                return {"error": f"Sentence range exceeds {MAX_SENTENCES_PER_READ} sentence limit."}

            lines = []
            for sent in spans[start_sentence:end_sentence]:
                line_text = _normalize_sentence_text(sent.text)
                lines.append(f"{sent.sentence_id} {line_text}")
            sub_text = "\n".join(lines)
            actual_start, actual_end = start_sentence, end_sentence

            # Record read in ledger
            if self.ledger:
                self.ledger.record_read(target_doc.id, actual_start, actual_end)

            return {
                "text": sub_text,
                "doc_id": target_doc.id,
                "start_sentence": actual_start,
                "end_sentence": actual_end,
                "total_sentences": total_sentences,
            }

        except Exception as e:
            return {"error": str(e)}


class SearchDocumentRegexTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="search_document_regex",
            description="Searches documents using a regex pattern. Returns matches with sentence-context windows."
        )

    def get_input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "doc_id": {"type": "integer", "description": "Single document ID or -1 for all documents"},
                "doc_ids": {"type": "array", "items": {"type": "integer"}, "description": "Array of document IDs to search"},
                "flags": {"type": "array", "items": {"type": "string"}, "default": []},
                "context_sentences": {"type": "integer", "default": 2},
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
        context_sentences = args.get("context_sentences", 2)
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
                    spans = build_sentence_index(self.case_id, doc.id, text)
                    sentence_id = _find_sentence_id(spans, start_char)
                    if sentence_id is None:
                        continue

                    ctx = max(0, int(context_sentences))
                    ctx_start = max(0, sentence_id - ctx)
                    ctx_end = min(len(spans), sentence_id + ctx + 1)
                    sentence_ids = list(range(ctx_start, ctx_end))
                    snippet_lines = [
                        f"{spans[sid].sentence_id} {_normalize_sentence_text(spans[sid].text)}"
                        for sid in sentence_ids
                    ]
                    snippet = "\n".join(snippet_lines)

                    doc_matches.append({
                        "start_sentence": ctx_start,
                        "end_sentence": ctx_end,
                        "match_sentence": sentence_id,
                        "start_char": start_char,
                        "end_char": end_char,
                        "sentence_ids": sentence_ids,
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

        # Build response as a list of {key, extracted} entries to match formatter expectations.
        extracted_by_key: Dict[str, List[Dict[str, Any]]] = {}
        for item in current_state.items:
            if item.bin_id in target_keys:
                extracted_by_key.setdefault(item.bin_id, []).append(
                    {
                        "value": item.value,
                        "evidence": item.evidence.model_dump(),
                    }
                )

        ordered_keys: List[str] = []
        if items_arg:
            ordered_keys = [key for key in items_arg if key in target_keys]
        elif item_arg != "all":
            ordered_keys = [item_arg]
        else:
            ordered_keys = list(definitions.keys())

        checklist_list = []
        for key in ordered_keys:
            if key not in target_keys:
                continue
            checklist_list.append(
                {
                    "key": key,
                    "extracted": extracted_by_key.get(key, []),
                }
            )

        completion_stats = self.store.get_completion_stats() if hasattr(self.store, "get_completion_stats") else {}
        return {"checklist": checklist_list, "completion_stats": completion_stats}


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
                                                    "document_id": {"type": "integer"},
                                                    "sentence_ids": {"type": "array", "items": {"type": "integer"}},
                                                },
                                                "required": ["document_id", "sentence_ids"],
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
                resolved_items = []
                for entry in items:
                    evidence_list = entry.get("evidence", [])
                    resolved_evidence = [
                        _resolve_sentence_evidence(self.case_id, ev) for ev in evidence_list
                    ]
                    resolved_items.append({"value": entry.get("value", ""), "evidence": resolved_evidence})
                self.store.update_key(key, resolved_items)
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
                                                    "document_id": {"type": "integer"},
                                                    "sentence_ids": {"type": "array", "items": {"type": "integer"}},
                                                },
                                                "required": ["document_id", "sentence_ids"],
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
                resolved_items = []
                for entry in items:
                    evidence_list = entry.get("evidence", [])
                    resolved_evidence = [
                        _resolve_sentence_evidence(self.case_id, ev) for ev in evidence_list
                    ]
                    resolved_items.append({"value": entry.get("value", ""), "evidence": resolved_evidence})
                self.store.append_to_key(key, resolved_items)
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
