# System Architecture

## Overview
The Legal Case Summarization Prototype is a full-stack Retrieval-Augmented Generation (RAG) system designed to produce high-quality legal summaries via a "Human-in-the-Loop" (HITL) workflow. Unlike standard chat-to-doc apps, it employs a **Checklist-First** architecture where evidence is first extracted, structured, and verified by a human before any prose is written.

### Key Capabilities
- **Structured Evidence Extraction**: Converts raw legal docs into "Evidence Bins" (JSON).
- **Async Summary Generation**: Non-blocking generation pipeline with polling.
- **Conversational Refinement**: Chat assistant with "Patch" capabilities (Diff-based editing).
- **Offline-Ready Caching**: Smart caching of evidence to avoid re-reading documents.

---

## 🏗 Backend Architecture (`/backend`)

The backend is a **FastAPI** service built on modular routers and services.

### 1. Core Services (`app/services/`)

#### 🧠 LLM Service (`llm.py`)
- **Adapter Pattern**: Abstracts providers (OpenAI, Ollama, Mock).
- **Reasoning Handling**: Automatically strips `<think>` tags from reasoning models (e.g., DeepSeek-R1, Qwen-2.5) to ensure clean output.
- **Mock Mode**: Deterministic backend for zero-cost UI testing (`LEGAL_CASE_USE_MOCK_LLM=true`).

#### 📝 Checklist Service (`checklists.py`)
- **Purpose**: The "Knowledge Base" of the case.
- **Extraction**: Uses `generate_structured` to fill 30+ specific evidence fields defined in `item_specific_info_improved.json`.
- **Hybrid Data Model**:
  - **AI Items**: Extracted automatically. Immutable by user (can be deleted/hidden).
  - **User Items**: Manually added by attorney. Stored in `user_items` list.
- **Caching**: Uses **Signature Hash** (SHA256 of `CaseID + DocumentContent + Version`). If docs change, cache invalidates.

#### 📄 Summary Service (`summary.py`)
- **Workflow**:
  1.  **Sort**: Orders documents (Docket vs Evidence).
  2.  **Retrieve**: Fetches *only* the **Checklist Items** (Evidence).
  3.  **Generate**: Prompts LLM with Evidence Items + "One-Shot" Style Example.
- **Concurrency**: Uses `BackgroundTasks` to run generation off the main thread.
- **Storage**: In-memory job tracking (`_summary_jobs`) with simple ID polling.

#### 💬 Chat Service (`chat.py`)
- **Context Injection**: Accepts `context` payload (highlighted text, storage items).
- **Tool Calling**:
  - **`commit_summary_edit`**: The only tool available to the assistant.
  - **Function**: Takes `summary_text`, returns a success signal.
  - **Result**: The Chat API response includes `summary_update` field, triggering the frontend patch flow.

### 2. Data Persistence (`app/data/`)
- **Flat DB**: The system uses a lightweight JSON-file database (NoSQL-style) located in `backend/app/data/flat_db/`.
- **Stores**:
  - `case_document_store.py`: Persists document text and metadata.
  - `checklist_store.py`: Persists extracted evidence collections.

### 3. External Integrations
#### 🏛 `app.services.clearinghouse`
**`ClearinghouseClient`**
- `__init__(api_key)`: Configures the client.
- `fetch_case_documents(case_id) -> Tuple[List[Document], str]`: Fetches case metadata, documents, and docket from Clearinghouse.net API and converts them to the internal `Document` schema.

---

## 🖥 Frontend Architecture (`/frontend`)

The frontend is a **React 19 + Vite** Single Page Application.

### 1. State Management (`features/workspace/state/`)
The app uses a custom Context + Hooks pattern (effectively a Store) rather than Redux/Zustand directly.

*   **`useSummaryStore.js`** (The Complex One):
    *   **Polling**: Manages `pollSummaryJob` loop (1.5s interval).
    *   **Patching Engine**:
        *   Receives full text from backend.
        *   Computes **Word-Level Diffs** client-side using `diff-words`.
        *   Manages `patchAction` state (Applied/Reverted/Stale).
*   **`useChecklistStore.js`**:
    *   **Derived State**: computes `highlightsByDocument` to map evidence items back to document offsets for highlighting.

### 2. Component Hierarchy
*   **`SummaryWorkspace`**: Top-level layout manager.
    *   **`ChecklistPanel`**: Displays evidence bins. Supports "Add Item" via floating tooltip.
    *   **`SummaryPanel`**: The writing surface. Renders the Draft and the Diff Overlays.
    *   **`DocumentsPanel`**: Full-text viewer. Handles text selection and highlighting.
    *   **`ChatPanel`**: Right-side drawer. Handles "Context Stapling" (via Tab key).

---

## 🔄 Critical Workflows

### 1. The "Checklist-First" Loop
This is the defining workflow of the application:
1.  **Ingestion**: User uploads documents -> Backend caches them.
2.  **Extraction**: Backend runs extraction → Populates `Verification Checklist`.
3.  **Human Verification**:
    *   Attorney reviews Checklist.
    *   *Missing Fact?* User highlights text in Document -> Clicks "Add Item".
4.  **Generation**: User clicks "Generate Summary".
    *   Backend prompts LLM using **Verified Checklist** (AI + User items).
5.  **Result**: A high-accuracy first draft.

### 2. The "Chat & Patch" Loop
1.  **Critique**: Attorney highlights a paragraph in the Summary.
2.  **Context**: Attorney presses `Tab` -> Text is "stapled" to Chat Input.
3.  **Instruction**: Attorney sends: "Fix this date error."
4.  **Tool Execution**:
    *   LLM calls `commit_summary_edit(new_full_text)`.
    *   Backend returns `new_full_text` in API response.
5.  **Diffing**:
    *   Frontend compares `old_text` vs `new_text`.
    *   Generates `[insert]`, `[delete]` patches.
6.  **Review**: Attorney sees Red/Green lines in the editor and clicks "Accept".

---

## 🧩 Data Models

### Document Reference
```json
{
  "id": 1,
  "title": "Complaint",
  "content": "...",
  "ecf_number": 1,
  "is_docket": true
}
```

### Checklist Item
```json
{
  "bin_id": "dates",
  "value": "May 17, 2024",
  "evidence": {
    "document_id": 1,
    "start_offset": 100,
    "end_offset": 112,
    "text": "filed on May 17, 2024"
  }
}
```

### Summary Job
```json
{
  "id": "uuid",
  "status": "pending | running | succeeded | failed",
  "summary_text": "Final prose..."
}
```
