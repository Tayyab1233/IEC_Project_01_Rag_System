# AI Usage Log

This document serves as the mandatory, auditable log of all AI prompts, models, configurations, and file modifications executed across all development turns in accordance with **Rule 1** in [GEMINI.md](file:///d:/IEC_Project_01_Rag_System/GEMINI.md).

---

## AI Tools & Configurations Overview
- **Development Environment**: Antigravity IDE
- **Core Reasoning Model**: Gemini 3.8 Flash High (`Antigravity IDE - Gemini 3.8 Flash High`)
- **Generation Model (Runtime)**: `gemini-3.5-flash-lite` (temperature = 0.1, response_mime_type = "application/json")
- **Embedding Model (Runtime)**: `BAAI/bge-m3` dense + sparse hybrid embeddings
- **Fallback Embedding Model**: `models/gemini-embedding-001` (active if RAM > 6.5 GB)
- **Vector Database**: Qdrant (local disk storage at `./qdrant_data`, cosine metric)
- **Relational Database**: SQLite in Write-Ahead Logging (WAL) mode via SQLAlchemy async

---

## Audit Log Entries

### Entry #1: Initial Project Scaffold and Strict Architectural Rules
- **Step / Prompt #**: 1
- **Date & Time**: 2026-11-24 11:27:25 +05:00
- **Model & Tool Used**: `Antigravity IDE - Gemini 3.8 Flash High`
- **Key Configuration/Settings**:
  - `GENERATION_MODEL`: `gemini-3.5-flash-lite`
  - `EMBEDDING_MODEL`: `BAAI/bge-m3`
  - `FALLBACK_EMBEDDING_MODEL`: `models/gemini-embedding-001`
  - `CHUNK_SIZE`: 450 tokens
  - `CHUNK_OVERLAP`: 60 tokens
  - `RETRIEVAL_TOP_K`: 18
  - `CONTEXT_CHUNKS`: 15
  - `MIN_SIMILARITY`: 0.25
  - `MAX_QUESTION_CHARS`: 1000
  - `MAX_UPLOAD_MB`: 20 MB
  - `API_TIMEOUT_SECONDS`: 30 s
  - `TEMPERATURE`: 0.1
  - `DATABASE_URL`: `sqlite+aiosqlite:///./rag_service.db` (WAL mode enabled)
  - `QDRANT_PATH`: `./qdrant_data`
- **Exact Prompt Text**:
```text
We are building the Production RAG Service (IEC Portfolio Project 1, deadline Wednesday 25 Nov 2026) from scratch in this empty workspace.

First, create a root `GEMINI.md` file (plain Markdown, no YAML frontmatter) with these strict project rules so every future session follows them:
1. AUTOMATIC AI USAGE LOGGING (MANDATORY ON EVERY TURN): Every time you execute any prompt in this workspace, you MUST automatically append a new entry to `docs/AI_USAGE.md` recording: Step/Prompt #, Date & Time, Exact Prompt Text, Model & Tool Used (`Antigravity IDE - Gemini 3.8 Flash High`), Key Configuration/Settings, and Files Created/Updated. Never skip updating `docs/AI_USAGE.md`.
2. Stack: FastAPI (`create_app()` factory in `backend/app/main.py`, routes only—no business logic in `main.py`), SQLite in WAL mode via SQLAlchemy (`users`, `documents`, `chunks`, `query_logs` with `sha256_hash` per user for 409 dedupe and document `status`), and Qdrant in local disk mode (`QdrantClient(path="./qdrant_data")`, cosine distance, mandatory `user_id` and `document_id` payload filters).
3. Extraction & Chunking: PyMuPDF (`fitz`) page-by-page with Markdown tables and repeated header/footer stripping; `python-docx` tracking section headings; TXT/MD direct read. Recursive splitter (~450 tokens, ~60 overlap) with a pre-split pass that merges short standalone label/badge lines (<40 chars directly above a heading, like "Tactic 1") into that heading's chunk.
4. Retrieval & Generation: `BAAI/bge-m3` embeddings (with `gemini-embedding-001` API fallback if RAM > 6.5 GB), dense + sparse RRF hybrid search, `MIN_SIMILARITY = 0.25`. `google-genai` SDK (`gemini-3.5-flash-lite` pinned in `config.py`, `temperature=0.1`) with `response_mime_type="application/json"` and Pydantic `response_schema` (`answerable`, `answer`, `cited_chunk_ids`). Python validates every cited ID against retrieved chunks and maps IDs to file names and pages.
5. Guardrails: Pre-retrieval input check blocking prompt-injection/jailbreak overrides (`400`) and >1000 chars (`422`); escape `<source>` and `<question>` tags inside untrusted document chunks (`re.compile(r"<(/?)(sources?|question)\b", re.IGNORECASE)`); scan uploaded chunks for hidden instructions; output check scanning for canary strings, API keys, and `.env` secrets.
6. Frontend: Plain HTML, CSS, and vanilla JS served by FastAPI (`frontend/`) with upload/delete, cited answers, and a retrieved-chunks panel showing chunk count, text, and similarity scores.
7. Code Quality & Git: Type hints and docstrings on every module/class/function; secrets in `.env` only; timeouts and retries on external calls; async I/O; unified JSON errors (`code`, `message`, `request_id`); structured logging (`X-Request-ID`, latency, tokens, no secrets).

Second, execute Phase 1 right now:
1. Create `.gitignore` (ignoring `.env`, `qdrant_data/`, `*.db`, `*.sqlite*`, `uploads/`, `sample_corpus/`, `__pycache__/`, `.venv/`, `.pytest_cache/`), `.env.example` (with `GEMINI_API_KEY=`, `ANTHROPIC_API_KEY=`, `JWT_SECRET=`, `APP_ENV=development`), and `requirements.txt` with pinned versions (`fastapi`, `uvicorn[standard]`, `sqlalchemy`, `aiosqlite`, `qdrant-client`, `google-genai>=3.0.0`, `pymupdf`, `python-docx`, `langchain-text-splitters`, `sentence-transformers`, `ragas`, `pytest`, `httpx`, `python-multipart`, `passlib[bcrypt]`, `pyjwt`, `slowapi`, `pydantic-settings`).
2. Create `backend/app/config.py` using `pydantic-settings` with pinned model IDs (`GENERATION_MODEL="gemini-3.5-flash-lite"`, `EMBEDDING_MODEL="BAAI/bge-m3"`), `CHUNK_SIZE=450`, `CHUNK_OVERLAP=60`, `RETRIEVAL_TOP_K=18`, `CONTEXT_CHUNKS=15`, `MIN_SIMILARITY=0.25`, `MAX_QUESTION_CHARS=1000`, `MAX_UPLOAD_MB=20`, and `API_TIMEOUT_SECONDS=30`.
3. Create `backend/app/schemas.py` with Pydantic v2 models for document metadata/responses, `/ask` request & response (`answerable`, `answer`, `citations`, `retrieved_chunks` with scores, `chunk_count`, `latency_ms`, `request_id`), and unified error responses.
4. Create `backend/app/db.py` configuring SQLite in WAL mode with SQLAlchemy models for `User`, `Document`, `Chunk`, and `QueryLog`.
5. Create `backend/app/main.py` using `create_app()` with `X-Request-ID` middleware, structured timing logs, unified exception handlers (`400`, `404`, `409`, `413`, `415`, `422`, `429`, `503`), and `GET /health`.
6. Create empty package folders (`backend/app/ingestion/`, `evals/`, `tests/`, `notebooks/`, `frontend/`, `docs/`) and create `docs/AI_USAGE.md` with an overview of the AI tools/models/configurations used and Entry #1 logging this prompt.
7. Run `git init`, verify `.env` is ignored, commit this scaffold to `main` with message `"chore: initial project scaffold and rules"`, and create/switch to branch `feature/ingestion`.
```
- **Files Created/Updated**:
  - [GEMINI.md](file:///d:/IEC_Project_01_Rag_System/GEMINI.md)
  - [.gitignore](file:///d:/IEC_Project_01_Rag_System/.gitignore)
  - [.env.example](file:///d:/IEC_Project_01_Rag_System/.env.example)
  - [requirements.txt](file:///d:/IEC_Project_01_Rag_System/requirements.txt)
  - [backend/app/__init__.py](file:///d:/IEC_Project_01_Rag_System/backend/app/__init__.py)
  - [backend/app/config.py](file:///d:/IEC_Project_01_Rag_System/backend/app/config.py)
  - [backend/app/schemas.py](file:///d:/IEC_Project_01_Rag_System/backend/app/schemas.py)
  - [backend/app/db.py](file:///d:/IEC_Project_01_Rag_System/backend/app/db.py)
  - [backend/app/main.py](file:///d:/IEC_Project_01_Rag_System/backend/app/main.py)
  - [backend/app/ingestion/__init__.py](file:///d:/IEC_Project_01_Rag_System/backend/app/ingestion/__init__.py)
  - [evals/__init__.py](file:///d:/IEC_Project_01_Rag_System/evals/__init__.py)
  - [tests/__init__.py](file:///d:/IEC_Project_01_Rag_System/tests/__init__.py)
  - [tests/conftest.py](file:///d:/IEC_Project_01_Rag_System/tests/conftest.py)
  - [tests/test_health.py](file:///d:/IEC_Project_01_Rag_System/tests/test_health.py)
  - [notebooks/.gitkeep](file:///d:/IEC_Project_01_Rag_System/notebooks/.gitkeep)
  - [frontend/.gitkeep](file:///d:/IEC_Project_01_Rag_System/frontend/.gitkeep)
  - [docs/AI_USAGE.md](file:///d:/IEC_Project_01_Rag_System/docs/AI_USAGE.md)
