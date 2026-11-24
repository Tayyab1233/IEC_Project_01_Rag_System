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


### Entry #2: Move 2 - File Upload, Extraction, Label-Merging Chunking, Deduplication, and Document Endpoints
- **Step / Prompt #**: 2
- **Date & Time**: 2026-11-24 12:14:39 +05:00
- **Model & Tool Used**: `Antigravity IDE - Gemini 3.8 Flash High`
- **Key Configuration/Settings**:
  - `GENERATION_MODEL`: `gemini-3.5-flash-lite`
  - `EMBEDDING_MODEL`: `BAAI/bge-m3` (Fallback: `models/gemini-embedding-001`)
  - `CHUNK_SIZE`: 450 tokens (~1800 characters)
  - `CHUNK_OVERLAP`: 60 tokens (~240 characters)
  - `RETRIEVAL_TOP_K`: 18
  - `CONTEXT_CHUNKS`: 15
  - `MIN_SIMILARITY`: 0.25
  - `MAX_QUESTION_CHARS`: 1000
  - `MAX_UPLOAD_MB`: 20 MB
  - `API_TIMEOUT_SECONDS`: 30 s
  - `TEMPERATURE`: 0.1
  - `VECTOR_STORE`: Qdrant Local Disk mode (`./qdrant_data`), cosine distance, collection `rag_chunks`
  - `SQLITE_MODE`: Write-Ahead Logging (WAL) mode via SQLAlchemy async
- **Exact Prompt Text**:
```text
Follow `GEMINI.md` (remember to append Entry #2 to `docs/AI_USAGE.md`, and add `pytest-asyncio` to `requirements.txt`). We are on branch `feature/ingestion` implementing Move 2: File Upload, Extraction, Label-Merging Chunking, Deduplication, and Document Management.

Build the following modules cleanly with full type hints, docstrings, and async support:
1. `backend/app/ingestion/validator.py`:
   - Validate file extension and MIME/magic bytes for `.pdf`, `.docx`, `.txt`, and `.md` (raise unified `415 Unsupported Media Type` otherwise).
   - Enforce `MAX_UPLOAD_MB` from `config.py` (`413 Payload Too Large` if exceeded) and reject empty 0-byte files (`400 Bad Request`).
   - Compute `sha256` hash of raw file bytes so duplicate uploads per user return `409 Conflict`.
2. `backend/app/ingestion/extractor.py`:
   - PDF (`import pymupdf`): extract text page-by-page, detect tables via `page.find_tables()` and convert them to Markdown (`table.to_markdown()`), strip repeated page headers/footers appearing across >60% of pages, and return `400 Bad Request` ("No extractable text found; scanned PDFs are not supported") if total extracted text is under 20 characters.
   - DOCX (`python-docx`): read paragraphs and tables in document order while tracking the active heading (`Heading 1/2/3`) as the `page_or_section` citation label.
   - TXT & MD: read UTF-8 text directly with section/line metadata.
3. `backend/app/ingestion/chunker.py`:
   - Implement a pre-split normalization pass that detects short standalone badge/label lines (<40 chars, e.g. "Tactic 1" or "Section A") sitting directly before a heading and merges them into that heading line so labels are never stranded at the end of a previous chunk.
   - Split text using `RecursiveCharacterTextSplitter` (~450 tokens / ~1800 chars, ~60 tokens / ~240 chars overlap) and prepend `[File: {file_name} | Location: {page_or_section}]` to each chunk before embedding.
   - Scan chunks for suspicious embedded prompt-injection phrases (e.g., "ignore previous instructions") and flag `has_injection_warning=True` in metadata without executing them.
4. `backend/app/ingestion/vector_store.py`:
   - Wrap `QdrantClient(path="./qdrant_data")` (cosine distance, collection `rag_chunks`), supporting `BAAI/bge-m3` embeddings (with automatic fallback to `gemini-embedding-001` via `google-genai` if `EMBEDDING_MODEL` starts with `gemini`).
   - Store payload `{user_id, document_id, file_name, page_or_section, chunk_index, text, sha256_hash, has_injection_warning}` and implement `delete_by_document_id(user_id, document_id)`.
5. `backend/app/ingestion/service.py` & `backend/app/main.py` routes:
   - Wire `POST /documents` (`201 Created`), `GET /documents` (`200 OK`), `GET /documents/{doc_id}` (`200` / `404`), and `DELETE /documents/{doc_id}` (`204 No Content` / `404`, deleting from both Qdrant and SQLite). Keep `main.py` thin—routes only call `ingestion/service.py`.
6. `tests/test_ingestion.py` & `notebooks/01_ingestion_pipeline.ipynb`:
   - Add automated tests in `tests/test_ingestion.py` (mocking the embedding model for fast offline execution) covering valid upload, `409` duplicate rejection, `400` empty/scanned PDF rejection, `415` bad file type, short-label `"Tactic 1"` heading merge, prompt-injection metadata flagging, and `DELETE /documents/{doc_id}`. Run `D:\conda_envs\dsc293_env\python.exe -m pytest` to verify all tests pass.
   - Create `notebooks/01_ingestion_pipeline.ipynb` demonstrating extraction, label-merging chunking, embedding, and Qdrant storage step-by-step on sample files.

Commit completed work to `feature/ingestion` with message `"feat(ingestion): add validation, extraction, label-merging chunker, and document endpoints"`.
```
- **Files Created/Updated**:
  - [requirements.txt](file:///d:/IEC_Project_01_Rag_System/requirements.txt)
  - [pytest.ini](file:///d:/IEC_Project_01_Rag_System/pytest.ini)
  - [backend/app/ingestion/validator.py](file:///d:/IEC_Project_01_Rag_System/backend/app/ingestion/validator.py)
  - [backend/app/ingestion/extractor.py](file:///d:/IEC_Project_01_Rag_System/backend/app/ingestion/extractor.py)
  - [backend/app/ingestion/chunker.py](file:///d:/IEC_Project_01_Rag_System/backend/app/ingestion/chunker.py)
  - [backend/app/ingestion/vector_store.py](file:///d:/IEC_Project_01_Rag_System/backend/app/ingestion/vector_store.py)
  - [backend/app/ingestion/service.py](file:///d:/IEC_Project_01_Rag_System/backend/app/ingestion/service.py)
  - [backend/app/ingestion/router.py](file:///d:/IEC_Project_01_Rag_System/backend/app/ingestion/router.py)
  - [backend/app/main.py](file:///d:/IEC_Project_01_Rag_System/backend/app/main.py)
  - [tests/conftest.py](file:///d:/IEC_Project_01_Rag_System/tests/conftest.py)
  - [tests/test_ingestion.py](file:///d:/IEC_Project_01_Rag_System/tests/test_ingestion.py)
  - [notebooks/01_ingestion_pipeline.ipynb](file:///d:/IEC_Project_01_Rag_System/notebooks/01_ingestion_pipeline.ipynb)
  - [docs/AI_USAGE.md](file:///d:/IEC_Project_01_Rag_System/docs/AI_USAGE.md)


### Entry #3: Move 3 - Hybrid Retrieval, Safety Guardrails, Grounded Generation, and Chat Endpoint
- **Step / Prompt #**: 3
- **Date & Time**: 2026-11-24 16:11:04 +05:00
- **Model & Tool Used**: `Antigravity IDE - Gemini 3.8 Flash High`
- **Key Configuration/Settings**:
  - `GENERATION_MODEL`: `gemini-2.5-flash`
  - `EMBEDDING_MODEL`: `BAAI/bge-m3` (Fallback: `models/gemini-embedding-001`)
  - `MIN_RELEVANCE_SCORE`: 0.25
  - `MIN_SIMILARITY`: 0.25
  - `RRF_K`: 60
  - `RETRIEVAL_TOP_K`: 18
  - `CONTEXT_CHUNKS`: 15
  - `TEMPERATURE`: 0.1
  - `MAX_QUESTION_CHARS`: 1000
  - `DEFAULT_INTERPRETER`: `D:\conda_envs\dsc293_env\python.exe`
- **Exact Prompt Text**:
```text
Do NOT run any Python/Conda environment discovery commands—our verified interpreter is strictly `D:\conda_envs\dsc293_env\python.exe`. First, create `.vscode/settings.json` with `{"python.defaultInterpreterPath": "D:\\conda_envs\\dsc293_env\\python.exe"}` so the IDE locks onto our Conda environment permanently. Follow `GEMINI.md` (remember to append Entry #3 to `docs/AI_USAGE.md`).

Next, merge `feature/ingestion` into `main` cleanly, then create and switch to a new branch `feature/rag-chat` for Move 3: Hybrid Retrieval, Safety Guardrails, Grounded Generation, and Chat Endpoint. Write all files first before running any terminal command:

1. `backend/app/rag/retriever.py`:
   - Implement multi-tenant hybrid retrieval strictly filtered by `user_id` (and optional `document_ids` filter).
   - Combine dense vector similarity from Qdrant (`rag_chunks`) with BM25 lexical scoring over the user's chunks (using `rank_bm25.BM25Okapi` if installed, or a clean pure-Python Okapi BM25 fallback) via Reciprocal Rank Fusion (RRF, k=60), returning the top-k ranked chunks with normalized relevance scores and citation metadata (`document_id`, `file_name`, `page_or_section`, `chunk_index`, `text`).
2. `backend/app/rag/guardrails.py`:
   - Input guardrail: detect direct prompt-injection or jailbreak attempts in user queries (e.g., "ignore previous instructions", "reveal system prompt", role-override patterns) and raise a unified `400 Bad Request` error before calling the LLM.
   - Evidence threshold check: if no chunks are retrieved or the top similarity score falls below `MIN_RELEVANCE_SCORE` from `config.py`, return a structured refusal (`refused=True`, clear explanation that the uploaded documents do not contain enough evidence) without hallucinating.
   - Context isolation helper: wrap retrieved chunks in `<context>` XML tags with explicit system instructions to ignore any imperative commands embedded inside document chunks.
3. `backend/app/rag/generator.py`:
   - Use the `google-genai` SDK (`genai.Client()`, model `gemini-2.5-flash` from `config.py`, low temperature `0.1`) to generate answers grounded strictly in the `<context>` chunks.
   - Enforce inline citations formatted as `[File: {file_name} | Location: {page_or_section}]` and extract structured `citations`, `model`, `latency_ms`, and token usage metadata into the response schema.
4. `backend/app/rag/service.py` & `backend/app/main.py` route:
   - Wire `POST /chat` (`200 OK`) delegating purely to `rag/service.py` (keeping `main.py` thin) and persist query/response audit logs in SQLite.
5. `tests/test_chat.py` & `notebooks/02_retrieval_and_rag.ipynb`:
   - Add automated tests in `tests/test_chat.py` (mocking Gemini API calls for fast offline testing) verifying: grounded citation answers, cross-tenant isolation (`user_b` cannot retrieve `user_a`'s docs), out-of-scope refusal when score is below threshold, and `400` rejection on query prompt injection.
   - Create `notebooks/02_retrieval_and_rag.ipynb` demonstrating hybrid RRF retrieval, guardrail checks, and grounded citation output.

Only after writing all files, run `D:\conda_envs\dsc293_env\python.exe -m pytest -v` to confirm all tests pass, then commit to `feature/rag-chat` with message `"feat(rag): add hybrid RRF retriever, safety guardrails, and grounded /chat endpoint"`.
```
- **Files Created/Updated**:
  - [.vscode/settings.json](file:///d:/IEC_Project_01_Rag_System/.vscode/settings.json)
  - [backend/app/config.py](file:///d:/IEC_Project_01_Rag_System/backend/app/config.py)
  - [backend/app/schemas.py](file:///d:/IEC_Project_01_Rag_System/backend/app/schemas.py)
  - [backend/app/rag/__init__.py](file:///d:/IEC_Project_01_Rag_System/backend/app/rag/__init__.py)
  - [backend/app/rag/retriever.py](file:///d:/IEC_Project_01_Rag_System/backend/app/rag/retriever.py)
  - [backend/app/rag/guardrails.py](file:///d:/IEC_Project_01_Rag_System/backend/app/rag/guardrails.py)
  - [backend/app/rag/generator.py](file:///d:/IEC_Project_01_Rag_System/backend/app/rag/generator.py)
  - [backend/app/rag/service.py](file:///d:/IEC_Project_01_Rag_System/backend/app/rag/service.py)
  - [backend/app/rag/router.py](file:///d:/IEC_Project_01_Rag_System/backend/app/rag/router.py)
  - [backend/app/main.py](file:///d:/IEC_Project_01_Rag_System/backend/app/main.py)
  - [tests/test_chat.py](file:///d:/IEC_Project_01_Rag_System/tests/test_chat.py)
  - [notebooks/02_retrieval_and_rag.ipynb](file:///d:/IEC_Project_01_Rag_System/notebooks/02_retrieval_and_rag.ipynb)
  - [docs/AI_USAGE.md](file:///d:/IEC_Project_01_Rag_System/docs/AI_USAGE.md)
