# Backend Service

FastAPI service that powers the Legal Case Summary Workspace.

## Quick Start
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Environment Variables (`.env`)
- `LEGAL_CASE_OLLAMA_BASE_URL` – URL for the local Ollama server (defaults to `http://127.0.0.1:11434`)
- `LEGAL_CASE_OLLAMA_MODEL` – Model tag (e.g. `qwen3:8b`)
- `LEGAL_CASE_USE_MOCK_LLM` – Set to `true` to use deterministic mock responses

## Primary Endpoints
| Method | Route | Description |
|--------|-------|-------------|
| `GET`  | `/cases/{case_id}/documents` | Returns catalogued documents with content |
| `POST` | `/cases/{case_id}/summary` | Starts an async summary job; returns a job id |
| `GET`  | `/cases/{case_id}/summary/{job_id}` | Fetches job status/result |
| `POST` | `/cases/{case_id}/suggestions` | Generates structured edit suggestions |
| `POST` | `/chat/session` | Creates a chat session |
| `POST` | `/chat/session/{session_id}/message` | Sends a message and returns AI + user turns |

Demo documents live in `app/data/documents` and are referenced by `catalog.json` until the Clearinghouse integration goes live.
