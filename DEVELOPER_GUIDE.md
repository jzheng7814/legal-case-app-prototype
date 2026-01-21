# Developer Guide

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- Node.js 18+
- Ollama (optional, for local inference)
- OpenAI API Key (optional, for cloud inference)

### 1. Backend Setup
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### Configuration
Copy `config/app.config.json.example` to `config/app.config.json`.
- Set `model.provider` to `"mock"`, `"openai"`, or `"ollama"`.
- If using `"mock"`, UI will work with fake data (Good for frontend dev).

#### Running the Server
```bash
python -m uvicorn app.main:app --reload --port 8000
```
API Docs will be at: `http://localhost:8000/docs`

### 2. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
App will be at: `http://localhost:5173`

---

## 🛠 Common Tasks

### 1. Adding a New Evidence Category
To teach the AI to extract a new type of fact (e.g., "Judge's Political Affiliation"):

1.  **Update Metadata**: Edit `backend/app/resources/checklists/v2/category_metadata.json`.
    *   Add a new entry with `id`, `label`, and `color`.
    *   Add the new item key to `members`.
2.  **Update Instructions**: Edit `backend/app/resources/checklists/item_specific_info_improved.json`.
    *   Add the item key and a detailed instruction on *how* to extract it.
3.  **Restart Backend**: The extraction prompt is rebuilt on startup.

### 2. Modifying the Summary Style
To change how the summary is written (tone, format):
*   Edit `backend/app/services/summary.py`.
*   Locate `STYLE_ONE_SHOT` variable.
*   Update the example text to reflect the new desired style.

### 3. Debugging "Chat & Patch"
If the AI suggests an edit but the Diff UI doesn't show up:
1.  Check Network Tab for `/chat/session/message` response.
2.  Look for `summary_update` field.
3.  If present, check Console for `diff-words` errors.
4.  If missing, the LLM failed to call the `commit_summary_edit` tool. Check `app/services/chat.py` system prompt.

---

## 🧪 Testing

### Using Mock Mode
This is the fastest way to develop.
1.  Set `provider: "mock"` in `app.config.json`.
2.  Upload any PDF.
3.  Checklist will populate with dummy items instantly.
4.  Summary will generate a placeholder text.
5.  Chat will reply with "MOCK RESPONSE".

This allows you to test the **entire UI state machine** (Polling, Patching, Checklist highlighting) without waiting for LLMs.
