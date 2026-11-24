"""Pytest fixtures for automated API and ingestion tests."""

import os
import shutil
import tempfile
from typing import AsyncGenerator, List

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import backend.app.db as app_db
from backend.app.db import Base
from backend.app.ingestion.vector_store import VectorStore, set_vector_store
from backend.app.main import create_app


STOP_WORDS = {
    "what", "is", "the", "for", "in", "and", "or", "to", "a", "an",
    "of", "with", "at", "by", "from", "on", "are", "must", "be", "it",
    "this", "that", "these", "those", "how", "do", "you", "its", "all",
}


def mock_embedder(texts: List[str]) -> List[List[float]]:
    """Fast deterministic mock embedder generating distinct 64-dim normalized vectors."""
    import hashlib

    dim = 64
    embeddings = []
    for text in texts:
        vec = [0.0] * dim
        words = text.lower().split()
        if not words:
            words = ["empty"]
        for word in words:
            h = int(hashlib.sha256(word.encode()).hexdigest(), 16)
            for i in range(dim):
                vec[i] += ((h >> (i * 2)) & 0x3) - 1.5
        norm = sum(x * x for x in vec) ** 0.5
        if norm > 0:
            embeddings.append([x / norm for x in vec])
        else:
            embeddings.append([1.0 / (dim ** 0.5)] * dim)
    return embeddings


@pytest.fixture(scope="session")
def temp_dir():
    """Create a temporary directory for test storage."""
    d = tempfile.mkdtemp(prefix="rag_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture(scope="session", autouse=True)
def setup_test_vector_store(temp_dir):
    """Configure a single session-wide test vector store using mock embeddings."""
    qdrant_path = os.path.join(temp_dir, "test_qdrant")
    store = VectorStore(
        path=qdrant_path,
        collection_name="test_rag_chunks",
        embedder=mock_embedder,
    )
    store.ensure_collection(vector_dim=64)
    set_vector_store(store)
    yield store
    try:
        store.client.close()
    except Exception:
        pass
    set_vector_store(None)


@pytest_asyncio.fixture
async def async_client(temp_dir) -> AsyncGenerator[AsyncClient, None]:
    """Provide an asynchronous HTTP test client with an isolated SQLite DB."""
    test_db_path = os.path.join(temp_dir, "test_rag.db")
    test_db_url = f"sqlite+aiosqlite:///{test_db_path}"

    engine = create_async_engine(test_db_url, echo=False)
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    orig_engine = app_db.engine
    orig_session_factory = app_db.async_session_factory
    app_db.engine = engine
    app_db.async_session_factory = session_factory

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client

    app_db.engine = orig_engine
    app_db.async_session_factory = orig_session_factory
    await engine.dispose()
