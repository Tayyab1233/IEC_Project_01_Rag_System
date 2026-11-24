# Production RAG Service - Strict Project Rules & Architecture

**Project**: IEC Portfolio Project 1 - Production RAG Service  
**Deadline**: Wednesday 25 Nov 2026  
**Workspace**: `d:\IEC_Project_01_Rag_System`

All future development sessions and automated agents MUST strictly adhere to these 7 architectural and operational rules.

---

## 1. Automatic AI Usage Logging (MANDATORY ON EVERY TURN)
Every time you execute any prompt in this workspace, you MUST automatically append a new entry to `docs/AI_USAGE.md` recording:
- **Step/Prompt #**: Sequential step number.
- **Date & Time**: ISO timestamp or human-readable local time.
- **Exact Prompt Text**: The complete, unaltered user prompt.
- **Model & Tool Used**: Exactly `Antigravity IDE - Gemini 3.8 Flash High`.
- **Key Configuration/Settings**: Model IDs, chunk size, overlap, temperature, retrieval thresholds, etc.
- **Files Created/Updated**: Explicit list of touched files with link references.

**NEVER skip updating `docs/AI_USAGE.md` on any turn.**

---

## 2. Technology Stack & Storage
- **Backend Framework**: FastAPI using application factory pattern (`create_app()` in `backend/app/main.py`). The `main.py` module defines route attachments and middleware only—NO business logic in `main.py`.
- **Relational Database**: SQLite in Write-Ahead Logging (WAL) mode (`PRAGMA journal_mode=WAL`, `PRAGMA synchronous=NORMAL`, `PRAGMA foreign_keys=ON`) managed via SQLAlchemy (async sessions with `aiosqlite`).
  - Tables: `users`, `documents`, `chunks`, `query_logs`.
  - Document deduplication: unique `(user_id, sha256_hash)` constraint returning HTTP `409 Conflict` on duplicate upload.
  - Document status lifecycle: `pending` -> `processing` -> `ready` (or `failed`).
- **Vector Database**: Qdrant running in local disk mode (`QdrantClient(path="./qdrant_data")`).
  - Cosine distance metric.
  - Mandatory payload filtering on `user_id` and `document_id` to enforce multi-tenant isolation.

---

## 3. Extraction & Chunking Architecture
- **PDF Extraction**: PyMuPDF (`fitz`) page-by-page extraction with Markdown table formatting and repeated running header/footer stripping across pages.
- **DOCX Extraction**: `python-docx` parser tracking hierarchical section headings (H1/H2/H3).
- **Text/Markdown**: Direct UTF-8 stream read.
- **Chunking Pipeline**:
  - Recursive text splitter targeting `~450 tokens` (~1800 characters) with `~60 tokens` overlap.
  - **Pre-split pass**: Automatically detect and merge short standalone badge/label lines (<40 characters directly above a heading, e.g., "Tactic 1") into that heading's chunk to prevent orphaned context fragments.

---

## 4. Retrieval & Generation Pipeline
- **Embeddings**: `BAAI/bge-m3` dense and sparse embeddings.
  - API Fallback: If available system RAM exceeds `6.5 GB` or falls below threshold, automatically fallback to `gemini-embedding-001` via API.
- **Hybrid Search**: Reciprocal Rank Fusion (RRF) combining dense vector similarity and sparse lexical BM25 matching.
- **Threshold**: Hard cutoff `MIN_SIMILARITY = 0.25`.
- **LLM Generation**: Google GenAI SDK (`google-genai>=3.0.0`) using model `gemini-3.5-flash-lite` pinned in `backend/app/config.py`, `temperature=0.1`.
  - Structured output: `response_mime_type="application/json"` with Pydantic `response_schema` (`answerable`, `answer`, `cited_chunk_ids`).
  - Citation Integrity: Server-side Python validation verifying every `cited_chunk_id` against the actually retrieved candidate chunks; automatically map validated IDs to source document names and page numbers.

---

## 5. Security & Guardrails
- **Pre-Retrieval Guard**:
  - Immediate regex and semantic scan blocking prompt-injection and jailbreak attempts returning HTTP `400 Bad Request`.
  - Input length limit: reject questions exceeding 1000 characters with HTTP `422 Unprocessable Entity`.
- **Chunk Sanitization**:
  - Escape prompt delimiter collision tags `<source>` and `<question>` in untrusted chunks using `re.compile(r"<(/?)(sources?|question)\b", re.IGNORECASE)`.
  - Scan uploaded chunks for hidden system instructions or privilege escalation triggers.
- **Post-Generation Guard**:
  - Output scanner checking for canary strings (`CANARY_CONFIDENTIAL_DO_NOT_EXFILTRATE`), leaked API keys, and environment secret leaks.

---

## 6. Frontend Presentation
- Plain HTML5, CSS3, and vanilla JavaScript served statically by FastAPI from `frontend/`.
- UI Features:
  - Document upload with drag-and-drop, progress status, and document deletion.
  - Query input with streaming/loading state.
  - Answer card with interactive inline citations.
  - Retrieved-chunks inspection panel displaying chunk count, source metadata, raw content, and similarity scores.

---

## 7. Code Quality & Engineering Standards
- **Type Hints & Documentation**: Full PEP 484 type annotations and docstrings on every module, class, and function.
- **Secrets Management**: Loaded strictly via `.env` through `pydantic-settings`. Never commit secrets or hardcode fallback tokens.
- **Resilience**: Configurable timeouts (`API_TIMEOUT_SECONDS=30`) and exponential backoff retries on external API calls.
- **Unified Error Responses**: Every error (400, 404, 409, 413, 415, 422, 429, 503, 500) returns a consistent JSON payload:
  ```json
  {
    "code": "ERROR_CODE",
    "message": "Human-readable error description",
    "request_id": "uuid4",
    "details": null
  }
  ```
- **Observability**: Structured JSON logging emitting `X-Request-ID`, endpoint, HTTP status, execution latency (ms), and token counts. Secrets and PII must be masked.
