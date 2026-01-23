# Backend Architecture & Context

## ⚡️ Quick Context
**Read this verification** to understand the backend without traversing the file tree.

### 1. System Overview
FastAPI backend handling legal case summarization via a **Checklist-First RAG** approach.

### 2. The Golden Workflow
1.  **Ingestion**: User uploads docs.
2.  **Checklist Extraction (AI)**: System extracts evidence into "bins" (e.g., Dates, Claims).
3.  **Human Verification**: User reviews/edits the checklist (add missing items, fix errors).
4.  **Summary Generation (AI)**: System generates prose **using the verified checklist** (not raw docs).
5.  **Refinement**: User chats with the AI to tweak the summary (AI uses `commit_summary_edit` tool, Frontend `diff-words`).

---

## 📚 Detailed API Reference

### 🧠 `app.services.llm` (LLM Service)
**`LLMService`**
- `__init__(settings: Settings)`: Initializes backend (OpenAI/Ollama/Mock).
- `generate_text(prompt: str, system: Optional[str]) -> str`: Simple text generation.
- `generate_structured(prompt: str, response_model: Type[BaseModel], ...) -> BaseModel`: Strict JSON generation.
- `chat(messages: List[LLMMessage], tools: Optional[List[dict]]) -> LLMResult`: Conversational completion.

**`LLMBackend`** (Abstract Base)
- `generate_response(...)`: Raw text generation.
- `generate_structured(...)`: JSON generation.
- `chat(...)`: Chat completion.

### 📝 `app.services.checklists` (Checklist Service)
**`EvidenceCollection`** (Data Class)
- `items: List[ChecklistItem]`: The core list of extracted facts.
- `signature: str`: Usage hash for caching.

**Functions**
- `extract_document_checklists(case_id, documents) -> EvidenceCollection`: Main entry point. Orchestrates parallel extraction.
- `_run_extraction(case_id, doc_chunk) -> LlmEvidenceCollection`: Internal. Calls LLM with `_DOCUMENT_PROMPT_TEMPLATE`.
- `add_user_item(case_id, item_payload) -> EvidenceCollection`: Manually inserts user evidence.
- `delete_user_item(case_id, item_id) -> EvidenceCollection`: Removes user evidence.

### 🤖 `app.services.agent` (Agentic Extraction)
**`AgentDriver`**
- `run()`: Executes the extraction loop until `max_steps` or stop decision.
- `_step()`: Builds snapshot -> gets action from Orchestrator -> executes Tool -> updates Ledger.

**`Orchestrator`**
- `decide_next_action(snapshot) -> ActionPlan`: Calls LLM with the formatted snapshot to choose the next tool.

**`SnapshotBuilder`**
- `build(step) -> Snapshot`: Aggregates:
    -   **Task Progress**: What items are missing/filled.
    -   **Document Catalog**: List of available files.
    -   **Action History**: Summary of recent moves.
    -   **Read Coverage**: Which parts of documents have been read.

**`Tools`**
- `ReadDocumentTool`: Reads a window of text (token-limited).
- `SearchDocumentRegexTool`: fast keyword search.
- `UpdateChecklistTool`: Writes extracted facts to the Store.

### 📄 `app.services.summary` (Summary Service)
**Functions**
- `start_summary_job(case_id, documents, instructions) -> SummaryJob`: Enqueues extraction + generation.
- `get_summary_job(case_id, job_id) -> SummaryJob`: Poll status.
- `_run_summary_job(job_id, case_id, documents, instructions)`: The worker function.
    1.  Calls `checklists.extract_document_checklists`.
    2.  Builds Prompt: `Evidence + Instructions + STYLE_ONE_SHOT`.
    3.  Calls `llm_service.generate_text`.

### 💬 `app.services.chat` (Chat Service)
**`ChatSession`** (Data Class)
- `messages: List[Message]`: History.
- `context: List[ContextItem]`: "Stapled" evidence (highlights, checklist items).

**Functions**
- `create_session() -> ChatSession`: New conversation.
- `send_message(session_id, user_message, context, summary_text) -> ChatResponse`:
    - Injects `_SYSTEM_PROMPT` (defines `commit_summary_edit`).
    - Calls `llm_service.chat_with_tools`.
    - Detects `tool_calls`. If `commit_summary_edit` called:
        - Returns `summary_update` (full text) in response.
        - Returns `summary_patches` (computed diffs) if backend-side diffing enabled (currently frontend-heavy).

### 💾 `app.data` (Data Layer)
**`case_document_store`**
- `save_documents(case_id, documents)`: Persists raw text.
- `get_documents(case_id)`: Retrieves text.

**`checklist_store`**
- `save_checklist(case_id, collection)`: Saves `EvidenceCollection` to JSON.
- `get_checklist(case_id)`: Loads collection.
- `save_user_items(case_id, items)`: Separate persistence for user overrides.

### 🏛 `app.services.clearinghouse` (External Ingestion)
**`ClearinghouseClient`**
- `__init__(api_key)`: Configures the client.
- `fetch_case_documents(case_id) -> Tuple[List[Document], str]`: Fetches case metadata, documents, and docket from Clearinghouse.net API and converts them to the internal `Document` schema.

