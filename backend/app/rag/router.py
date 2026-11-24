"""FastAPI router for grounded chat and retrieval endpoints.

Exposes:
- POST /chat (200 OK)
"""

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import get_db
from backend.app.ingestion.router import get_current_user_id
from backend.app.rag.service import handle_chat
from backend.app.schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post(
    "",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Grounded Chat Query",
)
async def chat_endpoint(
    request_body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
    request: Request = None,
) -> ChatResponse:
    """Submit a query to the production RAG pipeline with hybrid search and guardrails."""
    request_id = getattr(request.state, "request_id", "req_unknown")
    return await handle_chat(
        db=db,
        user_id=user_id,
        request=request_body,
        request_id=request_id,
    )
