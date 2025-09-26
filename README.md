# Legal Case Summary Workspace

This repository now houses the full stack for the Legal Case Summary Editor: a React workspace for attorneys on the frontend and a FastAPI service that orchestrates document retrieval, summary generation, structured AI suggestions, and context-aware chat.

## Repository Layout
- `frontend/` – Vite + React app that powers the authoring workspace
- `backend/` – FastAPI application that calls the local Ollama-hosted Qwen model and exposes REST endpoints
- `backend/app/data/` – Demo catalog and source documents used until Clearinghouse integration lands

## Backend Highlights
- `POST /cases/{case_id}/summary` kicks off an async job that composes summaries using the configured Qwen model (or a deterministic mock if needed)
- `POST /cases/{case_id}/suggestions` returns non-overlapping edit suggestions in a frontend-friendly format
- `POST /chat/session/{id}/message` streams chat turns while keeping context (summary, documents, highlights) consistent
- `GET /cases/{case_id}/documents` serves reference documents from the catalog, standing in for the future Clearinghouse fetch

## Frontend Updates
- The workspace now speaks to the backend via `src/services/apiClient.js`
- Summary generation triggers backend jobs and polls until completion, then automatically refreshes AI suggestions
- Chat routing creates real server-side sessions and relays highlight/suggestion context in each turn
- Document loading defaults to the backend and gracefully falls back to the bundled public assets when offline

## Prerequisites
| Component | Requirement |
|-----------|-------------|
| Backend   | Python 3.11+, pip/venv, [Ollama](https://ollama.com) with Qwen (`ollama pull qwen3:8b`) |
| Frontend  | Node.js 18+, npm |
| Shared    | macOS/Linux shell tools, two terminal panes (one per service) |

## Backend Setup
```bash
cd backend
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                 # review and adjust if needed
```
Key environment variables (all prefixed with `LEGAL_CASE_`):
- `OLLAMA_BASE_URL` and `OLLAMA_MODEL` point at your local Ollama instance and model tag
- `USE_MOCK_LLM=true` forces deterministic mock responses when the model is not available

Start the API server:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
The OpenAPI docs are available at `http://localhost:8000/docs`.

## Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
By default the client calls `http://localhost:8000`. Override this by setting `VITE_BACKEND_URL` in `frontend/.env` if needed.

## Daily Workflow
1. Launch the backend API (see above)
2. In another terminal, run `npm run dev` inside `frontend/`
3. Visit `http://localhost:5173`
4. Press “Generate with AI” – the UI will poll the summary job, render the text, pull suggestions, and surface them inline
5. Use the “Refresh Suggestions” button to re-sync edits after manual changes or new instructions
6. Open the chat panel to message the AI; selections or suggestions added via the Tab shortcut will be embedded in the request payload automatically

## Configuration Notes
- Demo data lives in `backend/app/data/documents`; swap these files or extend `catalog.json` to emulate other cases
- The backend caches summary jobs in-memory only; restart the server to clear state (persistent storage will plug in later)
- To shorten feedback loops during UI work, set `LEGAL_CASE_USE_MOCK_LLM=true` while the backend server is running

## Next Steps
- Replace the document catalog loader with the actual Clearinghouse client once credentials are available
- Persist chat and summary artifacts when the database tier is introduced
- Add automated tests that exercise the FastAPI routes and the React stores once the workflow stabilises

Happy lawyering! EOF
