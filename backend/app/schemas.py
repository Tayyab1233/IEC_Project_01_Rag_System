"""Pydantic v2 schemas for the Production RAG Service.

Includes document models, /ask request and response schemas, citation metadata,
retrieved chunk schemas, and unified error responses.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class DocumentStatus(str, Enum):
    """Lifecycle status of a document."""

    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class DocumentBase(BaseModel):
    """Base schema for document metadata."""

    filename: str
    file_size_bytes: int
    mime_type: str


class DocumentCreate(DocumentBase):
    """Schema for document registration."""

    sha256_hash: str
    user_id: str


class DocumentResponse(DocumentBase):
    """Response schema for document information."""

    id: str
    user_id: str
    sha256_hash: str
    status: DocumentStatus
    chunk_count: int = 0
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentListResponse(BaseModel):
    """Paginated or complete list of documents."""

    documents: List[DocumentResponse]
    total: int


class RetrievedChunk(BaseModel):
    """Schema representing a retrieved context chunk with similarity score."""

    chunk_id: str = Field(..., description="Unique ID of the chunk")
    document_id: str = Field(..., description="Parent document UUID")
    document_name: str = Field(..., description="Original filename of source document")
    content: str = Field(..., description="Raw text content of the chunk")
    score: float = Field(..., description="Dense/Sparse hybrid similarity score")
    page_number: Optional[int] = Field(default=None, description="Source page number if available")
    section_heading: Optional[str] = Field(default=None, description="Section heading if available")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional chunk metadata")


class Citation(BaseModel):
    """Validated citation linking answer facts to source chunks."""

    chunk_id: str = Field(..., description="ID of cited chunk")
    document_id: str = Field(..., description="Parent document UUID")
    document_name: str = Field(..., description="Filename of source document")
    page_number: Optional[int] = Field(default=None, description="Source page number")
    snippet: str = Field(..., description="Relevant text snippet cited in the answer")


class AskRequest(BaseModel):
    """Request payload for /ask query endpoint."""

    question: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="User question, maximum 1000 characters",
    )
    top_k: Optional[int] = Field(
        default=None,
        ge=1,
        le=50,
        description="Optional override for candidate retrieval count",
    )
    filter_document_ids: Optional[List[str]] = Field(
        default=None,
        description="Optional list of document IDs to restrict retrieval scope",
    )


class AskResponse(BaseModel):
    """Complete response payload for /ask query endpoint."""

    answerable: bool = Field(
        ..., description="True if sufficient context existed to answer factually"
    )
    answer: str = Field(..., description="Generated answer text or non-answerable message")
    citations: List[Citation] = Field(
        default_factory=list, description="Validated source citations"
    )
    retrieved_chunks: List[RetrievedChunk] = Field(
        default_factory=list, description="Full candidate chunks with similarity scores"
    )
    chunk_count: int = Field(..., description="Total retrieved chunks considered")
    latency_ms: float = Field(..., description="Total query execution latency in milliseconds")
    request_id: str = Field(..., description="Unique request tracing ID")


class LLMAnswerSchema(BaseModel):
    """Pydantic schema passed to Gemini structured JSON generation."""

    answerable: bool = Field(
        ..., description="Whether the context contains sufficient evidence to answer"
    )
    answer: str = Field(
        ..., description="Clear factual response based strictly on context"
    )
    cited_chunk_ids: List[str] = Field(
        default_factory=list, description="List of chunk IDs cited directly in the answer"
    )


class UnifiedErrorResponse(BaseModel):
    """Unified error response schema across all HTTP status codes."""

    code: str = Field(..., description="Short machine-readable error code")
    message: str = Field(..., description="Human-readable description of the error")
    request_id: str = Field(..., description="Unique request tracing ID")
    details: Optional[Any] = Field(
        default=None, description="Optional extra error details or validation issues"
    )


class HealthResponse(BaseModel):
    """Health check endpoint response schema."""

    status: str = "ok"
    app_env: str
    version: str = "1.0.0"
