"""Safety guardrails, prompt injection detection, and evidence validation.

Enforces:
- Pre-retrieval input guard: regex and semantic scan blocking prompt-injection and jailbreak attempts (400).
- Evidence threshold check: structured refusal if top score < MIN_RELEVANCE_SCORE (0.25).
- Context isolation helper: wraps chunks in <context> XML tags and sanitizes collision tags.
"""

import re
from typing import List, Optional, Tuple

from fastapi import HTTPException, status

from backend.app.config import get_settings
from backend.app.schemas import RetrievedChunkMetadata

# Regular expressions detecting direct prompt injection and jailbreak attempts
INJECTION_QUERY_PATTERNS = [
    re.compile(r"\b(ignore|disregard|forget)\s+(all\s+)?(previous|prior|above)\s+instructions\b", re.IGNORECASE),
    re.compile(r"\b(reveal|show|print|output|display)\s+(me\s+)?(your\s+)?(system\s+prompt|initial\s+prompt|developer\s+instructions)\b", re.IGNORECASE),
    re.compile(r"\b(you\s+are\s+now|now\s+act\s+as|pretend\s+you\s+are)\s+(an?\s+)?(unrestricted|developer|dan|jailbroken|god\s+mode)\b", re.IGNORECASE),
    re.compile(r"\b(jailbreak|dan\s+mode|developer\s+mode|override\s+rules|bypass\s+safety)\b", re.IGNORECASE),
    re.compile(r"<\s*(system|instruction|admin|developer)\s*>", re.IGNORECASE),
]

DELIMITER_COLLISION_PATTERN = re.compile(
    r"<(/?)(sources?|question|context|instructions?)\b", re.IGNORECASE
)


class RAGGuardrails:
    """Guardrails protecting query input, retrieved context, and generation safety."""

    @staticmethod
    def validate_user_query(query: str) -> None:
        """Validate input query against prompt-injection patterns and length constraints.

        Args:
            query: User's input prompt.

        Raises:
            HTTPException(422): If query exceeds maximum character limit.
            HTTPException(400): If prompt injection or jailbreak attempt is detected.
        """
        settings = get_settings()

        # Length check
        if len(query) > settings.MAX_QUESTION_CHARS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Query exceeds maximum allowed limit of {settings.MAX_QUESTION_CHARS} characters.",
            )

        # Prompt injection check
        clean_query = query.strip()
        for pattern in INJECTION_QUERY_PATTERNS:
            if pattern.search(clean_query):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Query rejected: Disallowed prompt injection or security policy override attempt detected.",
                )

    @staticmethod
    def evaluate_evidence_threshold(
        chunks: List[RetrievedChunkMetadata],
    ) -> Tuple[bool, Optional[str]]:
        """Determine whether retrieved chunks satisfy the minimum relevance threshold.

        Args:
            chunks: List of ranked candidate chunks from the retriever.

        Returns:
            Tuple of (is_sufficient_evidence, refusal_reason).
            If False, refusal_reason provides a polite, factual explanation.
        """
        settings = get_settings()
        min_threshold = settings.MIN_RELEVANCE_SCORE

        if not chunks:
            return (
                False,
                "The uploaded documents do not contain any relevant information to answer this question. Please upload relevant documentation.",
            )

        top_score = chunks[0].score
        if top_score < min_threshold:
            return (
                False,
                f"The available document evidence is insufficient (top relevance score {top_score:.2f} < threshold {min_threshold:.2f}). To prevent hallucination, an answer cannot be provided.",
            )

        return (True, None)

    @staticmethod
    def sanitize_chunk_text(text: str) -> str:
        """Sanitize delimiter collision tags within untrusted document chunks.

        Args:
            text: Raw chunk text.

        Returns:
            Sanitized text with escaped XML delimiter tags.
        """
        return DELIMITER_COLLISION_PATTERN.sub(r"&lt;\1\2", text)

    @staticmethod
    def format_isolated_context(chunks: List[RetrievedChunkMetadata]) -> str:
        """Wrap candidate chunks in an isolated <context> XML container.

        Enforces system instructions that document contents are untrusted data
        and must not be executed as system commands.

        Args:
            chunks: Retrieved chunks to format.

        Returns:
            Formatted XML context string.
        """
        settings = get_settings()
        selected_chunks = chunks[: settings.CONTEXT_CHUNKS]

        context_blocks = []
        for c in selected_chunks:
            sanitized = RAGGuardrails.sanitize_chunk_text(c.text)
            tag = f"[File: {c.file_name} | Location: {c.page_or_section}]"
            context_blocks.append(f"{tag}\n{sanitized}")

        inner_context = "\n\n---\n\n".join(context_blocks)
        return f"<context>\n{inner_context}\n</context>"
