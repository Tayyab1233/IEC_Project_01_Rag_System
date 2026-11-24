"""FastAPI application factory and middleware configuration.

Enforces:
- create_app() factory pattern
- X-Request-ID propagation & tracing middleware
- Structured timing logs
- Unified JSON exception handlers (400, 404, 409, 413, 415, 422, 429, 503, 500)
- GET /health endpoint
- Routes only (no business logic in main.py)
"""

import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.app.config import get_settings
from backend.app.db import init_db
from backend.app.ingestion.router import router as documents_router
from backend.app.rag.router import router as chat_router
from backend.app.schemas import HealthResponse, UnifiedErrorResponse

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("rag_service")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager for startup and shutdown hooks."""
    logger.info("Initializing database tables and SQLite WAL mode...")
    await init_db()
    logger.info("Database initialized successfully.")
    yield
    logger.info("Shutting down RAG Service application.")


def create_app() -> FastAPI:
    """Create and configure an instance of the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version="1.0.0",
        description="Production RAG Service API with hybrid retrieval and strict safety guardrails.",
        lifespan=lifespan,
    )

    # -------------------------------------------------------------------------
    # Middleware: X-Request-ID & Structured Request Latency Logging
    # -------------------------------------------------------------------------
    @app.middleware("http")
    async def request_tracing_and_timing_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        start_time = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            logger.error(
                "Unhandled error during request",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round(duration_ms, 2),
                    "error": str(exc),
                },
            )
            raise exc

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        response.headers["X-Request-ID"] = request_id

        logger.info(
            f"{request.method} {request.url.path} status={response.status_code} "
            f"latency={duration_ms:.2f}ms request_id={request_id}"
        )
        return response

    # -------------------------------------------------------------------------
    # Unified Error Handlers (400, 404, 409, 413, 415, 422, 429, 503, 500)
    # -------------------------------------------------------------------------
    def get_req_id(request: Request) -> str:
        return getattr(request.state, "request_id", str(uuid.uuid4()))

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        req_id = get_req_id(request)
        logger.warning(f"Validation error on {request.url.path}: {exc.errors()} [request_id={req_id}]")
        error_payload = UnifiedErrorResponse(
            code="VALIDATION_ERROR",
            message="Input validation failed.",
            request_id=req_id,
            details=exc.errors(),
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_payload.model_dump(),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        req_id = get_req_id(request)
        status_code = exc.status_code

        # Map standard status codes to machine-readable error codes
        code_mapping = {
            status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
            status.HTTP_404_NOT_FOUND: "NOT_FOUND",
            status.HTTP_409_CONFLICT: "CONFLICT_DUPLICATE",
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE: "PAYLOAD_TOO_LARGE",
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: "UNSUPPORTED_MEDIA_TYPE",
            status.HTTP_422_UNPROCESSABLE_ENTITY: "UNPROCESSABLE_ENTITY",
            status.HTTP_429_TOO_MANY_REQUESTS: "RATE_LIMIT_EXCEEDED",
            status.HTTP_503_SERVICE_UNAVAILABLE: "SERVICE_UNAVAILABLE",
        }
        error_code = code_mapping.get(status_code, f"HTTP_{status_code}")

        detail_msg = exc.detail if isinstance(exc.detail, str) else "An HTTP error occurred."
        details_extra = exc.detail if not isinstance(exc.detail, str) else None

        logger.warning(
            f"HTTPException {status_code} ({error_code}) on {request.url.path}: "
            f"{detail_msg} [request_id={req_id}]"
        )

        error_payload = UnifiedErrorResponse(
            code=error_code,
            message=detail_msg,
            request_id=req_id,
            details=details_extra,
        )
        return JSONResponse(
            status_code=status_code,
            content=error_payload.model_dump(),
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        req_id = get_req_id(request)
        logger.exception(f"Internal server error on {request.url.path} [request_id={req_id}]: {exc}")
        error_payload = UnifiedErrorResponse(
            code="INTERNAL_SERVER_ERROR",
            message="An unexpected server error occurred. Please try again later.",
            request_id=req_id,
            details=str(exc) if settings.DEBUG else None,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_payload.model_dump(),
        )

    # -------------------------------------------------------------------------
    # Core Health Route (No business logic in main.py)
    # -------------------------------------------------------------------------
    @app.get(
        "/health",
        response_model=HealthResponse,
        summary="Service Health Check",
        tags=["System"],
    )
    async def health_check() -> HealthResponse:
        """Return the current service operational status and environment."""
        return HealthResponse(
            status="ok",
            app_env=settings.APP_ENV,
            version="1.0.0",
        )

    # -------------------------------------------------------------------------
    # Root Redirect to Interactive UI
    # -------------------------------------------------------------------------
    @app.get("/", include_in_schema=False)
    async def root_redirect():
        """Redirect root URL to the interactive frontend UI."""
        return RedirectResponse(url="/ui")

    # -------------------------------------------------------------------------
    # Feature Routers (Routes only - no business logic in main.py)
    # -------------------------------------------------------------------------
    app.include_router(documents_router)
    app.include_router(chat_router)

    # -------------------------------------------------------------------------
    # Mount Frontend Web UI Static Files
    # -------------------------------------------------------------------------
    app.mount("/ui", StaticFiles(directory="frontend", html=True), name="frontend")

    return app


# Root application instance for ASGI servers (e.g. uvicorn backend.app.main:app)
app = create_app()
