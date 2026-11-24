"""Orchestration service for hybrid retrieval, guardrails, and grounded generation.

Coordinates:
- Input guardrail validation (rejecting prompt injections).
- Multi-tenant hybrid RRF retrieval strictly filtered by user_id.
- Evidence threshold verification (refusing out-of-scope/unsupported queries).
- Isolated XML context construction.
- Grounded generation via Google GenAI with inline citation parsing.
- Audit logging to SQLite QueryLog.
"""

import time
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import get_settings
from backend.app.db import QueryLog
from backend.app.ingestion.service import ensure_user_exists
from backend.app.rag.generator import get_generator
from backend.app.rag.guardrails import RAGGuardrails
from backend.app.rag.retriever import get_retriever
from backend.app.schemas import ChatRequest, ChatResponse


async def handle_chat(
    db: AsyncSession,
    user_id: str,
    request: ChatRequest,
    request_id: str,
) -> ChatResponse:
    """Handle an incoming chat inquiry with strict security and grounding.

    Args:
        db: Async database session.
        user_id: Active user identifier (multi-tenant boundary).
        request: Validated ChatRequest payload.
        request_id: Tracing request ID.

    Returns:
        ChatResponse with grounded answer or refusal.

    Raises:
        HTTPException(400): If prompt-injection attempt is detected.
        HTTPException(422): If input exceeds character limits.
    """
    start_time = time.perf_counter()
    settings = get_settings()
    await ensure_user_exists(db, user_id)

    # 1. Pre-Retrieval Input Guardrail Check
    RAGGuardrails.validate_user_query(request.message)

    # 2. Multi-Tenant Hybrid RRF Retrieval
    retriever = get_retriever()
    ranked_chunks = retriever.retrieve(
        query=request.message,
        user_id=user_id,
        top_k=request.top_k,
        filter_document_ids=request.filter_document_ids,
    )

    # 3. Evidence Threshold Check
    has_evidence, refusal_reason = RAGGuardrails.evaluate_evidence_threshold(ranked_chunks)

    if not has_evidence:
        latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
        refusal_msg = (
            refusal_reason
            or "I do not have enough factual evidence in the uploaded documents to answer this question."
        )

        # Log refusal to SQLite
        query_log = QueryLog(
            id=str(uuid.uuid4()),
            user_id=user_id,
            question=request.message,
            answerable=False,
            answer=refusal_msg,
            chunk_count=len(ranked_chunks),
            latency_ms=latency_ms,
            request_id=request_id,
        )
        db.add(query_log)
        await db.commit()

        return ChatResponse(
            answer=refusal_msg,
            refused=True,
            refusal_reason=refusal_reason,
            citations=[],
            retrieved_chunks=ranked_chunks,
            model=settings.GENERATION_MODEL,
            latency_ms=latency_ms,
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
            request_id=request_id,
        )

    # 4. Context Isolation (<context> XML encapsulation & tag sanitization)
    context_xml = RAGGuardrails.format_isolated_context(ranked_chunks)

    # 5. Grounded Generation & Inline Citation Extraction
    generator = get_generator()
    answer_text, citations, meta = generator.generate(
        query=request.message,
        context_xml=context_xml,
        retrieved_chunks=ranked_chunks,
    )

    total_latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

    # 6. Record Audit Query Log in SQLite
    query_log = QueryLog(
        id=str(uuid.uuid4()),
        user_id=user_id,
        question=request.message,
        answerable=True,
        answer=answer_text,
        chunk_count=len(ranked_chunks),
        latency_ms=total_latency_ms,
        request_id=request_id,
    )
    db.add(query_log)
    await db.commit()

    return ChatResponse(
        answer=answer_text,
        refused=False,
        refusal_reason=None,
        citations=citations,
        retrieved_chunks=ranked_chunks,
        model=meta.get("model", settings.GENERATION_MODEL),
        latency_ms=total_latency_ms,
        prompt_tokens=meta.get("prompt_tokens"),
        completion_tokens=meta.get("completion_tokens"),
        total_tokens=meta.get("total_tokens"),
        request_id=request_id,
    )
