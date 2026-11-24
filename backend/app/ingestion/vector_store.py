"""Vector store wrapper for Qdrant local disk mode.

Enforces:
- Local disk persistence via QdrantClient(path="./qdrant_data").
- Cosine distance metric on collection 'rag_chunks'.
- Dense embedding generation using BAAI/bge-m3 with Google GenAI fallback.
- Mandatory payload filtering on user_id and document_id for multi-tenant isolation.
- Support for delete_by_document_id(user_id, document_id).
"""

import os
import uuid
from typing import Any, Callable, Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from backend.app.config import get_settings


class VectorStore:
    """Manages Qdrant collections and vector embeddings."""

    def __init__(
        self,
        path: Optional[str] = None,
        collection_name: Optional[str] = None,
        embedder: Optional[Callable[[List[str]], List[List[float]]]] = None,
    ):
        """Initialize Qdrant client and embedding handler.

        Args:
            path: Directory path for Qdrant disk storage.
            collection_name: Name of Qdrant collection.
            embedder: Optional custom embedding function for dependency injection.
        """
        self.settings = get_settings()
        self.path = path or self.settings.QDRANT_PATH
        self.collection_name = collection_name or self.settings.QDRANT_COLLECTION
        os.makedirs(self.path, exist_ok=True)
        self.client = QdrantClient(path=self.path)
        self._custom_embedder = embedder
        self._st_model = None

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate dense vector embeddings for input texts.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors.
        """
        if not texts:
            return []

        # 1. Custom/mock embedder (injected for fast unit tests)
        if self._custom_embedder is not None:
            return self._custom_embedder(texts)

        # 2. Check if configured for Gemini embedding API fallback
        if (
            self.settings.EMBEDDING_MODEL.startswith("gemini")
            or self.settings.EMBEDDING_MODEL.startswith("models/gemini")
            or (self.settings.GEMINI_API_KEY and self.settings.APP_ENV == "api_embedding")
        ):
            from google import genai

            client = genai.Client(api_key=self.settings.GEMINI_API_KEY)
            response = client.models.embed_content(
                model=self.settings.FALLBACK_EMBEDDING_MODEL,
                contents=texts,
            )
            return [embedding.values for embedding in response.embeddings]

        # 3. Default: BAAI/bge-m3 via SentenceTransformer (lazy loaded)
        if self._st_model is None:
            from sentence_transformers import SentenceTransformer

            self._st_model = SentenceTransformer(self.settings.EMBEDDING_MODEL)

        embeddings = self._st_model.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()

    def ensure_collection(self, vector_dim: int = 1024) -> None:
        """Ensure that the Qdrant collection exists with cosine distance.

        Args:
            vector_dim: Dimensionality of the vectors (default 1024 for bge-m3).
        """
        if not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=vector_dim, distance=Distance.COSINE),
            )

    def upsert_chunks(
        self,
        user_id: str,
        document_id: str,
        file_name: str,
        sha256_hash: str,
        chunks: List[Any],
    ) -> None:
        """Embed and upsert processed chunks into Qdrant with tenant payload isolation.

        Args:
            user_id: ID of the owning user.
            document_id: UUID of parent document.
            file_name: Original file name.
            sha256_hash: Hash of the raw file content.
            chunks: List of ProcessedChunk objects.
        """
        if not chunks:
            return

        texts_to_embed = [chunk.content for chunk in chunks]
        embeddings = self.get_embeddings(texts_to_embed)
        vector_dim = len(embeddings[0]) if embeddings else 1024
        self.ensure_collection(vector_dim=vector_dim)

        points: List[PointStruct] = []
        for chunk, vector in zip(chunks, embeddings):
            # Deterministic UUID5 for Qdrant point ID
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{document_id}_{chunk.chunk_index}"))
            payload: Dict[str, Any] = {
                "user_id": user_id,
                "document_id": document_id,
                "file_name": file_name,
                "page_or_section": chunk.page_or_section,
                "chunk_index": chunk.chunk_index,
                "text": chunk.content,
                "raw_text": chunk.raw_text,
                "sha256_hash": sha256_hash,
                "has_injection_warning": chunk.has_injection_warning,
                "token_count": chunk.token_count,
            }
            points.append(PointStruct(id=point_id, vector=vector, payload=payload))

        self.client.upsert(collection_name=self.collection_name, points=points)

    def delete_by_document_id(self, user_id: str, document_id: str) -> None:
        """Delete all points belonging to a specific document for a user.

        Args:
            user_id: ID of owning user.
            document_id: UUID of document to remove.
        """
        if not self.client.collection_exists(self.collection_name):
            return

        delete_filter = Filter(
            must=[
                FieldCondition(key="user_id", match=MatchValue(value=user_id)),
                FieldCondition(key="document_id", match=MatchValue(value=document_id)),
            ]
        )
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=delete_filter,
        )

    def count_document_chunks(self, user_id: str, document_id: str) -> int:
        """Count points stored for a specific document.

        Args:
            user_id: ID of owning user.
            document_id: UUID of document.

        Returns:
            Number of indexed points.
        """
        if not self.client.collection_exists(self.collection_name):
            return 0

        res = self.client.count(
            collection_name=self.collection_name,
            count_filter=Filter(
                must=[
                    FieldCondition(key="user_id", match=MatchValue(value=user_id)),
                    FieldCondition(key="document_id", match=MatchValue(value=document_id)),
                ]
            ),
        )
        return res.count


# Global singleton instance
_vector_store_instance: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    """Return the global VectorStore singleton."""
    global _vector_store_instance
    if _vector_store_instance is None:
        _vector_store_instance = VectorStore()
    return _vector_store_instance


def set_vector_store(store: Optional[VectorStore]) -> None:
    """Override or reset the global VectorStore singleton (useful for tests)."""
    global _vector_store_instance
    _vector_store_instance = store
