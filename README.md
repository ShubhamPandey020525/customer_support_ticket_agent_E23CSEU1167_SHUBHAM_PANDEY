# Customer Support Ticket Agent

A text-based customer support agent that answers policy questions using a RAG knowledge base and collects information to raise support tickets through a multi-turn conversation. Built with FastAPI, Streamlit, LangGraph, ChromaDB, and an open-source LLM served locally via Ollama.

---

## Architecture

```text
┌──────────────────────────────────────────────────────┐
│                  Customer (Browser)                  │
└───────────────────────┬──────────────────────────────┘
                        │ HTTP (chat input)
┌───────────────────────▼──────────────────────────────┐
│              Streamlit UI  (port 8501)               │
│  - Session-aware chat with UUID session ID           │
│  - Source-document display (RAG answers)             │
│  - Ticket confirmation panel                         │
│  - Graceful error states for API/model failures      │
└───────────────────────┬──────────────────────────────┘
                        │ POST /chat
┌───────────────────────▼──────────────────────────────┐
│              FastAPI API  (port 8000)                │
│  GET  /health         → real pipeline readiness      │
│  POST /chat           → process one customer turn    │
│  GET  /tickets/{id}   → retrieve a created ticket    │
└───────────────────────┬──────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────┐
│           SupportPipeline (src/pipeline.py)          │
│  - Validates input / session management              │
│  - Invokes LangGraph workflow                        │
└──────────┬────────────────────────────┬──────────────┘
           │                            │
┌──────────▼────────┐        ┌──────────▼─────────────┐
│  LangGraph Agent  │        │  ChromaDB Vector Store  │
│  (src/llm/)       │        │  (knowledge_base/*.md)  │
│                   │        │  all-MiniLM-L6-v2 embed │
│  retrieve ──────► │──────► │                         │
│  decide           │        └─────────────────────────┘
│  answer           │
│  collect_or_create│◄──── Mock Ticket Tool
│                   │      (TicketRepository)
└───────────────────┘
```

**Flow:** Customer message → Streamlit → FastAPI → LangGraph workflow → RAG knowledge base + mock ticket tool → agent response → Streamlit display.

---

## Technology Stack

| Component | Library | Version |
|-----------|---------|---------|
| API | FastAPI + Uvicorn | ≥0.115 / ≥0.30 |
| UI | Streamlit | ≥1.40 |
| LLM client | langchain-openai (ChatOpenAI) | ≥0.3 |
| Agent framework | LangGraph | ≥0.2 |
| Vector store | ChromaDB | ≥0.5 |
| Embeddings | sentence-transformers/all-MiniLM-L6-v2 | ≥3.0 |
| LLM | Qwen2.5:3b (default) via Ollama | any |

> **LLM note:** Any OpenAI-compatible endpoint serving an open-source
> instruction-tuned model works. The default is Qwen2.5:3b via Ollama.
> No proprietary/closed model API is used.

---

## Requirements

- **Python 3.12** or newer (3.11+ works too)
- **Ollama** (or equivalent OpenAI-compatible local inference endpoint)
- ~500 MB disk space for the embedding model (downloaded once on first run)
- ~2 GB RAM for Qwen2.5:3b

---

## Setup

### Step 1 — Install Ollama and pull the model

Download Ollama from https://ollama.com and then:

```sh
ollama pull qwen2.5:3b
```

> **Alternative:** Any OpenAI-compatible endpoint (LM Studio, vLLM, Together AI
> with an open-source model) can be used by setting `LLM_BASE_URL` and
> `LLM_MODEL` in `.env`.

### Step 2 — Create a virtual environment

#### Windows (PowerShell)
```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

#### Linux / macOS
```sh
python3.12 -m venv .venv
source .venv/bin/activate
```

### Step 3 — Install dependencies

```sh
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Step 4 — Configure environment

#### Windows (PowerShell)
```powershell
Copy-Item .env.example .env
```

#### Linux / macOS
```sh
cp .env.example .env
```

Edit `.env` and set your values. **Never commit `.env` with real secrets.**

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible endpoint URL |
| `LLM_API_KEY` | `not-required` | API key (use `not-required` for Ollama) |
| `LLM_MODEL` | `qwen2.5:3b` | Model name to use |
| `API_BASE_URL` | `http://localhost:8000` | Used by Streamlit to reach FastAPI |
| `API_HOST` | `127.0.0.1` | FastAPI bind address |
| `API_PORT` | `8000` | FastAPI port |
| `STREAMLIT_HOST` | `127.0.0.1` | Streamlit bind address |
| `STREAMLIT_PORT` | `8501` | Streamlit port |
| `VECTOR_DB_PATH` | `.data/vector_db` | ChromaDB persistence directory |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | HuggingFace embedding model |
| `RAG_COLLECTION` | `customer-support` | ChromaDB collection name |
| `RAG_TOP_K` | `3` | Number of chunks to retrieve per query |

---

## Running the Application

Start the API server first, then the UI in a separate terminal.

### Terminal 1 — FastAPI backend

#### Linux / macOS
```sh
uvicorn src.api.server:app --reload --host ${API_HOST:-127.0.0.1} --port ${API_PORT:-8000}
```

#### Windows (PowerShell)
```powershell
uvicorn src.api.server:app --reload --host 127.0.0.1 --port 8000
```

The API docs are available at `http://localhost:8000/docs`.

### Terminal 2 — Streamlit UI

#### Linux / macOS
```sh
streamlit run streamlit_app.py --server.address ${STREAMLIT_HOST:-127.0.0.1} --server.port ${STREAMLIT_PORT:-8501}
```

#### Windows (PowerShell)
```powershell
streamlit run streamlit_app.py --server.address 127.0.0.1 --server.port 8501
```

Open `http://localhost:8501` in your browser.

---

## Running Tests

```sh
pytest -v
```

The test suite runs without a running API server or LLM — it uses mocks and
the local ChromaDB with real embeddings for retriever tests.

> **Note:** The retriever integration tests (`test_retriever.py`) download the
> embedding model (~90 MB) on first run. Subsequent runs use the local cache.

---

## Manual API Testing

### Check health
```sh
curl http://localhost:8000/health
```

### Send a chat message (Linux / macOS)
```sh
curl -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"demo-1","message":"How long does standard shipping take?"}'
```

### Windows PowerShell equivalent
```powershell
Invoke-RestMethod -Method POST -Uri http://localhost:8000/chat `
  -ContentType 'application/json' `
  -Body '{"session_id":"demo-1","message":"How long does standard shipping take?"}'
```

You can also use the interactive `/docs` interface at `http://localhost:8000/docs`.

---

## Knowledge Base

The four supplied Markdown documents in `knowledge_base/`:

| File | Topic |
|------|-------|
| `shipping.md` | Standard and express delivery times |
| `payments.md` | Duplicate charges and payment issues |
| `returns.md` | Return window and refund timeline |
| `accounts.md` | Password reset and account security |

---

## Tech Stack Substitutions and Deviations

See [`DECISIONS.md`](./DECISIONS.md) for the full rationale behind every
architectural decision, including:

- Why `build_support_workflow` was extended to accept dependency parameters
- The "mid-session requirement" interpretation (not defined in the main guide)
- Exclusion of voice features (mentioned once as apparent boilerplate in §10)
- Relevance threshold of 0.30 for "not in KB" detection

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `GET /health` returns 503 | Retriever initialisation failed (model not downloaded or ChromaDB error) | Check terminal logs; ensure `VECTOR_DB_PATH` is writable |
| LLM calls time out | Ollama not running, or wrong `LLM_BASE_URL` | Run `ollama serve` and `ollama pull qwen2.5:3b` |
| "Cannot connect to backend" in UI | FastAPI not running | Start `uvicorn` in a separate terminal |
| Duplicate chunks warning | Normal on cold start; second run is fast | Idempotent by design — safe to ignore |
| Embedding model downloads slowly | First-run behaviour | Downloads once and caches locally |
