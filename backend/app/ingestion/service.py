"""Business logic and orchestration for document ingestion and management.

Coordinates:
- Validation (size, MIME, magic bytes, SHA-256 deduplication).
- Extraction (PDF with markdown tables, DOCX with headings, TXT/MD).
- Label-merging chunking and injection warning detection.
- Vector store indexing in Qdrant.
- Relational metadata tracking in SQLite.
"""

import json
import logging
import uuid
from typing import Optional

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import Chunk, Document, User
from backend.app.ingestion.chunker import chunk_document
from backend.app.ingestion.extractor import DocumentExtractor
from backend.app.ingestion.validator import check_duplicate_document, validate_file
from backend.app.ingestion.vector_store import get_vector_store
from backend.app.schemas import (
    DocumentListResponse,
    DocumentResponse,
    DocumentStatus,
)

logger = logging.getLogger("rag_service.ingestion")


async def ensure_user_exists(db: AsyncSession, user_id: str) -> User:
    """Ensure a user record exists in SQLite to satisfy foreign key constraints.

    Args:
        db: Async database session.
        user_id: User identifier.

    Returns:
        User record.
    """
    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            id=user_id,
            email=f"{user_id}@example.local",
            hashed_password="mock_hashed_password",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user


async def upload_and_ingest_document(
    db: AsyncSession,
    user_id: str,
    file: UploadFile,
) -> DocumentResponse:
    """Process an uploaded document through validation, extraction, chunking, and indexing.

    Args:
        db: Async database session.
        user_id: ID of uploading user.
        file: FastAPI UploadFile object.

    Returns:
        DocumentResponse with populated metadata and READY status.

    Raises:
        HTTPException(400, 409, 413, 415): On validation or extraction failure.
    """
    await ensure_user_exists(db, user_id)

    # 1. Read file content
    try:
        content = await file.read()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read uploaded file: {exc}",
        )

    filename = file.filename or "uploaded_file"

    # 2. Validate file attributes (size, magic bytes, hash)
    validation = validate_file(filename=filename, content=content)

    # 3. Check for duplicates per user (409 Conflict)
    await check_duplicate_document(
        db=db, user_id=user_id, sha256_hash=validation.sha256_hash
    )

    # 4. Create document entity with PENDING / PROCESSING status
    doc_id = str(uuid.uuid4())
    doc = Document(
        id=doc_id,
        user_id=user_id,
        filename=filename,
        sha256_hash=validation.sha256_hash,
        file_size_bytes=validation.file_size_bytes,
        mime_type=validation.mime_type,
        status=DocumentStatus.PROCESSING.value,
        chunk_count=0,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    try:
        # 5. Extract document content
        extracted_doc = DocumentExtractor.extract(
            filename=filename,
            content=content,
            mime_type=validation.mime_type,
        )

        # 6. Chunk text with label-merging pass
        processed_chunks = chunk_document(extracted_doc)

        # 7. Index chunks in Qdrant vector store
        vector_store = get_vector_store()
        vector_store.upsert_chunks(
            user_id=user_id,
            document_id=doc_id,
            file_name=filename,
            sha256_hash=validation.sha256_hash,
            chunks=processed_chunks,
        )

        # 8. Save chunk records to SQLite
        for chunk in processed_chunks:
            meta = {
                "page_or_section": chunk.page_or_section,
                "has_injection_warning": chunk.has_injection_warning,
            }
            db_chunk = Chunk(
                id=chunk.chunk_id,
                document_id=doc_id,
                user_id=user_id,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                token_count=chunk.token_count,
                page_number=chunk.page_number,
                section_heading=chunk.section_heading,
                metadata_json=json.dumps(meta),
            )
            db.add(db_chunk)

        # 9. Mark document as READY
        doc.status = DocumentStatus.READY.value
        doc.chunk_count = len(processed_chunks)
        await db.commit()
        await db.refresh(doc)

        logger.info(
            f"Successfully ingested doc {doc_id} ({filename}) with {len(processed_chunks)} chunks."
        )
        return DocumentResponse.model_validate(doc)

    except HTTPException:
        doc.status = DocumentStatus.FAILED.value
        await db.commit()
        raise

    except Exception as exc:
        logger.exception(f"Unexpected error ingesting document {doc_id}: {exc}")
        doc.status = DocumentStatus.FAILED.value
        doc.error_message = str(exc)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Document ingestion failed: {exc}",
        )


async def list_documents(db: AsyncSession, user_id: str) -> DocumentListResponse:
    """Retrieve all documents belonging to a user.

    Args:
        db: Async database session.
        user_id: User identifier.

    Returns:
        DocumentListResponse containing documents and total count.
    """
    stmt = (
        select(Document)
        .where(Document.user_id == user_id)
        .order_by(Document.created_at.desc())
    )
    result = await db.execute(stmt)
    docs = result.scalars().all()

    return DocumentListResponse(
        documents=[DocumentResponse.model_validate(d) for d in docs],
        total=len(docs),
    )


async def get_document(
    db: AsyncSession, user_id: str, document_id: str
) -> DocumentResponse:
    """Retrieve metadata for a single document.

    Args:
        db: Async database session.
        user_id: User identifier.
        document_id: UUID of document.

    Returns:
        DocumentResponse.

    Raises:
        HTTPException(404): If document does not exist for user.
    """
    stmt = select(Document).where(
        Document.id == document_id, Document.user_id == user_id
    )
    result = await db.execute(stmt)
    doc = result.scalar_one_or_none()

    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found.",
        )

    return DocumentResponse.model_validate(doc)


async def delete_document(db: AsyncSession, user_id: str, document_id: str) -> None:
    """Delete a document from both SQLite and Qdrant.

    Args:
        db: Async database session.
        user_id: User identifier.
        document_id: UUID of document to delete.

    Raises:
        HTTPException(404): If document does not exist for user.
    """
    stmt = select(Document).where(
        Document.id == document_id, Document.user_id == user_id
    )
    result = await db.execute(stmt)
    doc = result.scalar_one_or_none()

    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found.",
        )

    # 1. Delete vectors from Qdrant
    vector_store = get_vector_store()
    vector_store.delete_by_document_id(user_id=user_id, document_id=document_id)

    # 2. Delete document from SQLite (chunks cascade deleted via foreign key)
    await db.delete(doc)
    await db.commit()

    logger.info(f"Deleted document {document_id} and its associated vectors.")
