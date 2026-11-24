"""FastAPI router for document management endpoints.

Exposes:
- POST /documents (201 Created)
- GET /documents (200 OK)
- GET /documents/{doc_id} (200 OK / 404 Not Found)
- DELETE /documents/{doc_id} (204 No Content / 404 Not Found)
"""

from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import get_db
from backend.app.ingestion.service import (
    delete_document,
    get_document,
    list_documents,
    upload_and_ingest_document,
)
from backend.app.schemas import DocumentListResponse, DocumentResponse

router = APIRouter(prefix="/documents", tags=["Documents"])


def get_current_user_id(request: Request) -> str:
    """Extract authenticated or demo user_id from headers.

    Enforces multi-tenant isolation by tagging all documents and queries with this ID.
    """
    return request.headers.get("X-User-ID", "default_user")


@router.post(
    "",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and Ingest Document",
)
async def upload_document_endpoint(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> DocumentResponse:
    """Upload, extract, chunk, and index a document in both SQLite and Qdrant."""
    return await upload_and_ingest_document(db=db, user_id=user_id, file=file)


@router.get(
    "",
    response_model=DocumentListResponse,
    status_code=status.HTTP_200_OK,
    summary="List User Documents",
)
async def list_documents_endpoint(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> DocumentListResponse:
    """Retrieve all uploaded documents for the active user."""
    return await list_documents(db=db, user_id=user_id)


@router.get(
    "/{doc_id}",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Document Details",
)
async def get_document_endpoint(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> DocumentResponse:
    """Fetch metadata for a single document by its UUID."""
    return await get_document(db=db, user_id=user_id, document_id=doc_id)


@router.delete(
    "/{doc_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Document",
)
async def delete_document_endpoint(
    doc_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
) -> None:
    """Delete a document and purge all its vectors from Qdrant and records from SQLite."""
    await delete_document(db=db, user_id=user_id, document_id=doc_id)
    return None
