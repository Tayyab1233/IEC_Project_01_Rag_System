"""Validation utilities for incoming document uploads.

Enforces:
- File extension and MIME/magic bytes validation for .pdf, .docx, .txt, .md (415).
- Maximum upload size (413) and non-empty file requirement (400).
- SHA-256 hash calculation and user-scoped deduplication check (409).
"""

import hashlib
import io
import os
import zipfile
from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import get_settings
from backend.app.db import Document

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}

MIME_TYPE_MAPPING = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
}


@dataclass
class ValidationResult:
    """Encapsulates validated document metadata."""

    filename: str
    file_size_bytes: int
    mime_type: str
    sha256_hash: str
    extension: str


def validate_file(filename: str, content: bytes) -> ValidationResult:
    """Validate file extension, magic bytes, size, and compute SHA-256 hash.

    Args:
        filename: Name of the uploaded file.
        content: Raw bytes of the uploaded file.

    Returns:
        ValidationResult with verified metadata.

    Raises:
        HTTPException(400): If file is empty (0 bytes).
        HTTPException(413): If file exceeds MAX_UPLOAD_MB.
        HTTPException(415): If extension or magic bytes are unsupported.
    """
    settings = get_settings()

    # 1. Non-empty check (400 Bad Request)
    file_size = len(content)
    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file: 0-byte uploads are not permitted.",
        )

    # 2. Maximum file size check (413 Payload Too Large)
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if file_size > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Payload too large: File size ({file_size} bytes) exceeds maximum limit of {settings.MAX_UPLOAD_MB}MB.",
        )

    # 3. File extension check (415 Unsupported Media Type)
    _, ext = os.path.splitext(filename.lower())
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported media type: Extension '{ext}' is not supported. Allowed formats: .pdf, .docx, .txt, .md",
        )

    # 4. Magic bytes & content integrity verification
    mime_type = MIME_TYPE_MAPPING[ext]
    if ext == ".pdf":
        if not content.startswith(b"%PDF"):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Unsupported media type: Invalid PDF header magic bytes.",
            )
    elif ext == ".docx":
        # DOCX files are zip archives starting with PK\x03\x04 and containing word/document.xml
        if not content.startswith(b"PK\x03\x04"):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Unsupported media type: Invalid DOCX archive magic bytes.",
            )
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                namelist = zf.namelist()
                if not any("word/document.xml" in name for name in namelist):
                    raise HTTPException(
                        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                        detail="Unsupported media type: Corrupt DOCX archive missing word/document.xml.",
                    )
        except zipfile.BadZipFile:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Unsupported media type: Corrupt or invalid DOCX zip archive.",
            )
    elif ext in {".txt", ".md"}:
        # Plain text must be valid UTF-8 and contain no binary null bytes
        if b"\x00" in content:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Unsupported media type: Binary null bytes detected in text file.",
            )
        try:
            content.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Unsupported media type: Text file must be UTF-8 encoded.",
            )

    # 5. Compute SHA-256 hash
    sha256_hash = hashlib.sha256(content).hexdigest()

    return ValidationResult(
        filename=filename,
        file_size_bytes=file_size,
        mime_type=mime_type,
        sha256_hash=sha256_hash,
        extension=ext,
    )


async def check_duplicate_document(
    db: AsyncSession, user_id: str, sha256_hash: str
) -> Optional[Document]:
    """Check if a document with identical SHA-256 hash exists for the given user.

    Args:
        db: Async database session.
        user_id: The ID of the uploading user.
        sha256_hash: The SHA-256 hash of the uploaded file bytes.

    Returns:
        None if no duplicate exists.

    Raises:
        HTTPException(409): If an identical file already exists for this user.
    """
    stmt = select(Document).where(
        Document.user_id == user_id, Document.sha256_hash == sha256_hash
    )
    result = await db.execute(stmt)
    existing_doc = result.scalar_one_or_none()

    if existing_doc is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Duplicate document detected: A document with identical SHA-256 hash "
                f"('{sha256_hash}') already exists (ID: {existing_doc.id}, Name: {existing_doc.filename})."
            ),
        )

    return None
