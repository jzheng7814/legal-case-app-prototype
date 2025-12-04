# Legal Case Summary Workspace

Full-stack prototype for an attorney-facing case summary editor. The React/Vite frontend gives writers a document-rich workspace, while the FastAPI backend handles document retrieval, checklist extraction, summary generation, and a tool-enabled chat loop that can commit edits back into the draft.

## Repository Layout
- `frontend/` – React 19 + Vite workspace
- `backend/` – FastAPI service plus background jobs, LLM abstraction, Clearinghouse client stub, and structured schemas.
- `backend/app/data/` – Bundled demo catalog (`catalog.json` + `.txt` sources) and lightweight JSON “flat DB” caches for documents and checklist signatures.
- `backend/app/resources/checklists/` – Prompt template and curated checklist metadata used by evidence extraction.
- `backend/logs/` – Rotating JSONL logs written by `app/logging_utils.py`, including every LLM request/response for auditing.
- `tools/`, `scratch/` – Local experimentation helpers (not part of the deployed app).

## Platform Capabilities
### Document ingestion & caching
- `GET /cases/{case_id}/documents` serves documents (-1 if demo documents, otherwise pulled from Clearinghouse).
- Remote pulls are cached both in-memory and on disk (`backend/app/data/flat_db/case_documents.json`) so repeated loads are instant and survive process restarts.
- The same endpoint prefetches LLM-derived checklists in the background and returns `checklist_status` (`pending`, `cached`, `fallback`) so the UI can reflect readiness.
- The frontend document service gracefully falls back to static assets in `frontend/public/documents/` if the API is offline, and attorneys can inject ad‑hoc uploads from the home screen (files stay in memory on the client).

### Summary generation pipeline
- `POST /cases/{case_id}/summary` spins up an async job (`app/services/summary.py`) that merges selected documents, applies instructions, and calls the configured LLM provider through `LLMService`.
- Providers are configured in `backend/config/app.config.json` (OpenAI, Ollama, or deterministic mock) and loaded via `LEGAL_CASE_CONFIG_PATH`. Temperature/output limits live in the config defaults, not the code.
- Jobs track `pending → running → succeeded/failed`; the frontend polls `GET /cases/{case_id}/summary/{job_id}` until the body text is ready and then snapshots the version history locally.

### Checklist extraction pipeline
- Evidence extraction runs over the authoritative documents (`app/services/checklists.py`), using prompt templates and metadata from `app/resources/checklists/`.
- Extraction is cached per case (hashed signature + payload persisted in `backend/app/data/flat_db/document_checklist_items_v2.json`) and re-used whenever the source documents haven’t changed.
- Checklist collections feed the checklist UI and can be pushed into chat context so the assistant can close gaps.

### Conversational assistant & patch pipeline
- Chat sessions (`/chat/session`) persist in-process; every `send_message` call includes the current summary, lightweight document metadata, and the structured context items gathered from highlights or checklist rows.
- The backend chat service (`app/services/chat.py`) uses tool calling: the LLM can invoke `commit_summary_edit` to deliver a full replacement summary, or return granular patches which the UI shows in `SummaryPatchPanel`.
- All LLM calls (text, structured, chat) are logged in JSON for traceability, and `LLMService` automatically strips `<think>` reasoning tags before returning text to clients.

### Attorney workspace (React)
- **Home screen** (`frontend/src/features/home/HomeScreen.jsx`): enter a case ID (default `-1` for demo data) or upload PDFs/DOC/DOCX/TXT; uploads are read client-side and forwarded to the workspace as synthetic documents.
- **Summary panel**: shows the live draft, toggles between edit/read modes, runs “Generate with AI” (which triggers backend jobs and polls), tracks a local version history dropdown, and surfaces AI patch overlays you can click, preview, or revert.
- **Checklist panel**: contrasts document coverage, outlines reasoning/evidence spans, and lets you push an item (and its supporting text) into the chat context with one click.
- **Documents panel**: renders full-text evidence, highlights any spans referenced by checklist/chat context, and stays in sync with the summary when selections jump across panes.
- **Chat panel**: supports multiple sessions, shows context “chips,” deduplicates repeated selections, and lets you hit `Tab` from either the summary or document pane to staple the current highlight into the chat payload. When the AI issues a patch, the panel records the change log and the summary panel updates without manual copy/paste.

## API Surface
| Method | Route | Description |
|--------|-------|-------------|
| `GET`  | `/health/pulse` | Simple readiness probe. |
| `GET`  | `/cases/{case_id}/documents` | Returns documents, optional prefetched checklist data, and checklist status metadata. |
| `POST` | `/cases/{case_id}/summary` | Starts a background summary job; response contains the job envelope (ID + status). |
| `GET`  | `/cases/{case_id}/summary/{job_id}` | Poll job status/result until `succeeded`. |
| `POST` | `/chat/session` | Creates a server-side chat session. |
| `GET`  | `/chat/session/{session_id}` | Fetches existing session state. |
| `POST` | `/chat/session/{session_id}/message` | Sends a user turn with summary/document context; response may include summary patches or a full rewrite. |

All schemas live under `backend/app/schemas/` and are enforced both inbound (FastAPI validation) and outbound (Pydantic models from the LLM layer).

## Running Locally
### Prerequisites
| Component | Requirement |
|-----------|-------------|
| Backend | Python 3.11+, `pip`, virtualenv. |
| Frontend | Node.js 18+ (any modern npm). |
| LLM providers | One of: OpenAI API key, or [Ollama](https://ollama.com/) with a pulled model (default `qwen3:8b`). |
| Optional | macOS/Linux shell, two terminal panes, `make` (optional). |

### Backend setup
```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # edit values as needed
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend setup
```bash
cd frontend
npm install
cp .env.example .env             # optional; overrides API origin
npm run dev                      # launches on http://localhost:5173
```

### Local workflow
1. Start the FastAPI server.
2. Start `npm run dev` and open `http://localhost:5173`.
3. On the home screen, enter `-1` (demo catalog) or upload files, then “Proceed to Summary Editor”.
4. Click “Generate with AI” to queue a backend job; the UI shows job state, then inserts the returned text and takes a version snapshot.
5. Use `Tab` while text is selected (summary or document) to push the snippet into the chat context, ask a question, and optionally apply the AI’s patch via the patch panel.

## Configuration
### Backend environment (`LEGAL_CASE_*`)
| Variable | Purpose |
|----------|---------|
| `LEGAL_CASE_APP_NAME` | Display name in logs. |
| `LEGAL_CASE_ENVIRONMENT` | `development`/`production` (affects CORS + logging). |
| `LEGAL_CASE_USE_MOCK_LLM` | Force the deterministic mock backend (great for UI demos). |
| `LEGAL_CASE_CONFIG_PATH` | Path to the JSON model config (defaults to `config/app.config.json`). |
| `OPENAI_API_KEY` | Required when `model.provider` is `openai`. |
| `LEGAL_CASE_CLEARINGHOUSE_API_KEY` | Enables the Clearinghouse HTTP client; omit to stay in demo mode. |

`backend/config/app.config.json` controls the active provider, model IDs, timeouts, and defaults (temperature, max tokens). Switch providers by editing `model.provider` and filling in the corresponding block—no code changes needed.

### Frontend environment
| Variable | Purpose |
|----------|---------|
| `VITE_BACKEND_URL` | Base URL for API requests (defaults to `http://localhost:8000`). |

### Data, assets, and logs
- Demo documents: `backend/app/data/documents/*.txt` + `catalog.json`.
- API caches: `backend/app/data/flat_db/case_documents.json` and `document_checklist_items_v2.json`.
- Frontend fallback docs: `frontend/public/documents/`.
- LLM/file logs: `backend/logs/llm-*.log`, `backend/logs/clearinghouse-*.log`, etc.

## Using the Workspace Effectively
- **Versioning & patches**: Every AI-generated draft is saved in `useSummaryStore`’s `versionHistory`. The `SummaryPatchPanel` lists in-flight patches, lets you jump to the affected span, and revert a single patch or the full batch.
- **Checklist insights**: Each checklist column (documents vs summary) shows status, reasoning, and evidence ranges. Clicking the “Add to Chat” icon pushes a concise, cite-rich note into the chat context so the AI can fix missing elements.
- **Chat context shortcuts**: Selecting text and pressing `Tab` adds the snippet as a context chip. You can also pin arbitrary notes or checklist rows. The chat panel deduplicates overlapping ranges to keep payloads small.
- **Uploaded materials**: Files chosen on the home screen are treated as additional documents in the workspace session only—they aren’t persisted to the backend, which keeps compliance scopes clear during demos.

Happy lawyering!
