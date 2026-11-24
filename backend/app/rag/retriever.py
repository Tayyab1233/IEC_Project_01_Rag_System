"""Multi-tenant hybrid RRF retriever.

Combines dense vector similarity from Qdrant with BM25 lexical ranking
using Reciprocal Rank Fusion (RRF, k=60), strictly isolated by user_id.
"""

import math
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
)

from backend.app.config import get_settings
from backend.app.ingestion.vector_store import get_vector_store
from backend.app.schemas import RetrievedChunkMetadata


def tokenize(text: str) -> List[str]:
    """Tokenize text into lowercase alphanumeric words for BM25 matching."""
    return re.findall(r"\w+", text.lower())


class OkapiBM25:
    """Pure-Python implementation of the Okapi BM25 ranking algorithm."""

    def __init__(
        self,
        corpus: List[List[str]],
        k1: float = 1.5,
        b: float = 0.75,
    ):
        """Initialize BM25 index with tokenized corpus.

        Args:
            corpus: List of tokenized documents.
            k1: Term frequency saturation parameter.
            b: Document length normalization parameter.
        """
        self.corpus_size = len(corpus)
        self.k1 = k1
        self.b = b
        self.doc_lengths = [len(doc) for doc in corpus]
        self.avg_doc_len = (
            sum(self.doc_lengths) / self.corpus_size if self.corpus_size > 0 else 1.0
        )

        # Calculate document frequencies
        self.df: Dict[str, int] = {}
        self.term_freqs: List[Dict[str, int]] = []

        for doc in corpus:
            tf: Dict[str, int] = {}
            for term in doc:
                tf[term] = tf.get(term, 0) + 1
            self.term_freqs.append(tf)
            for term in tf:
                self.df[term] = self.df.get(term, 0) + 1

        # Calculate inverse document frequencies (IDF)
        self.idf: Dict[str, float] = {}
        for term, freq in self.df.items():
            self.idf[term] = math.log(
                1.0 + (self.corpus_size - freq + 0.5) / (freq + 0.5)
            )

    def get_scores(self, query_tokens: List[str]) -> List[float]:
        """Compute BM25 relevance scores for all documents in the corpus.

        Args:
            query_tokens: List of tokenized query terms.

        Returns:
            List of float BM25 scores aligned with corpus indices.
        """
        scores = [0.0] * self.corpus_size
        for term in query_tokens:
            if term not in self.idf:
                continue
            idf_val = self.idf[term]
            for i, tf_dict in enumerate(self.term_freqs):
                if term not in tf_dict:
                    continue
                tf = tf_dict[term]
                doc_len = self.doc_lengths[i]
                numerator = tf * (self.k1 + 1.0)
                denominator = tf + self.k1 * (
                    1.0 - self.b + self.b * (doc_len / self.avg_doc_len)
                )
                scores[i] += idf_val * (numerator / denominator)
        return scores


class HybridRetriever:
    """Performs multi-tenant hybrid RRF retrieval combining dense and sparse search."""

    def __init__(self):
        self.settings = get_settings()
        self.vector_store = get_vector_store()
        self.rrf_k = self.settings.RRF_K

    def retrieve(
        self,
        query: str,
        user_id: str,
        top_k: Optional[int] = None,
        filter_document_ids: Optional[List[str]] = None,
    ) -> List[RetrievedChunkMetadata]:
        """Execute hybrid search combining dense Qdrant search and lexical BM25 with RRF.

        Args:
            query: User search text.
            user_id: ID of the querying user (enforces multi-tenant isolation).
            top_k: Number of ranked chunks to return (defaults to RETRIEVAL_TOP_K).
            filter_document_ids: Optional subset of document UUIDs to restrict to.

        Returns:
            List of top-k RetrievedChunkMetadata sorted by composite RRF score descending.
        """
        limit = top_k or self.settings.RETRIEVAL_TOP_K
        client = self.vector_store.client
        collection_name = self.vector_store.collection_name

        if not client.collection_exists(collection_name):
            return []

        # ---------------------------------------------------------------------
        # 1. Multi-Tenant Payload Filter (Strictly Enforced)
        # ---------------------------------------------------------------------
        must_conditions = [
            FieldCondition(key="user_id", match=MatchValue(value=user_id))
        ]
        if filter_document_ids:
            must_conditions.append(
                FieldCondition(key="document_id", match=MatchAny(any=filter_document_ids))
            )

        qdrant_filter = Filter(must=must_conditions)

        # ---------------------------------------------------------------------
        # 2. Dense Vector Retrieval via Qdrant
        # ---------------------------------------------------------------------
        query_embeddings = self.vector_store.get_embeddings([query])
        dense_hits = []
        if query_embeddings:
            query_vector = query_embeddings[0]
            try:
                # Retrieve candidate points using cosine search above similarity cutoff
                search_res = client.search(
                    collection_name=collection_name,
                    query_vector=query_vector,
                    query_filter=qdrant_filter,
                    score_threshold=self.settings.MIN_SIMILARITY,
                    limit=max(limit * 2, 20),
                    with_payload=True,
                )
                dense_hits = search_res or []
            except Exception:
                dense_hits = []

        # ---------------------------------------------------------------------
        # 3. Sparse Lexical Retrieval via BM25
        # ---------------------------------------------------------------------
        # Scroll user's matching documents to build candidate lexical corpus
        scroll_res, _ = client.scroll(
            collection_name=collection_name,
            scroll_filter=qdrant_filter,
            limit=1000,
            with_payload=True,
        )

        all_points = scroll_res or []
        if not all_points and not dense_hits:
            return []

        # Index points by point_id
        point_by_id = {str(p.id): p for p in all_points}
        for hit in dense_hits:
            point_by_id[str(hit.id)] = hit

        points_list = list(point_by_id.values())
        corpus = [tokenize(p.payload.get("text", "")) for p in points_list]
        query_tokens = tokenize(query)

        bm25_model = OkapiBM25(corpus)
        bm25_scores = bm25_model.get_scores(query_tokens)

        # Rank BM25 hits with positive score
        bm25_ranked = sorted(
            [(point, score) for point, score in zip(points_list, bm25_scores) if score > 0.0],
            key=lambda x: x[1],
            reverse=True,
        )

        # ---------------------------------------------------------------------
        # 4. Reciprocal Rank Fusion (RRF)
        # ---------------------------------------------------------------------
        # Map point IDs to ranks (1-indexed)
        dense_rank_map: Dict[str, Tuple[int, float]] = {}
        for rank, hit in enumerate(dense_hits, start=1):
            dense_rank_map[str(hit.id)] = (rank, float(hit.score))

        bm25_rank_map: Dict[str, Tuple[int, float]] = {}
        for rank, (point, score) in enumerate(bm25_ranked, start=1):
            bm25_rank_map[str(point.id)] = (rank, score)

        # Candidate IDs must have matched dense (above cutoff) OR lexical (positive score)
        all_candidate_ids = set(dense_rank_map.keys()) | set(bm25_rank_map.keys())
        if not all_candidate_ids:
            return []

        max_possible_rrf = 2.0 / (self.rrf_k + 1.0)
        scored_candidates: List[RetrievedChunkMetadata] = []

        for pid in all_candidate_ids:
            point = point_by_id.get(pid)
            if not point or not point.payload:
                continue

            dense_rank, dense_score = dense_rank_map.get(pid, (1000, 0.0))
            bm25_rank, bm25_score = bm25_rank_map.get(pid, (1000, 0.0))

            rrf_score = 0.0
            if pid in dense_rank_map:
                rrf_score += 1.0 / (self.rrf_k + dense_rank)
            if pid in bm25_rank_map:
                rrf_score += 1.0 / (self.rrf_k + bm25_rank)

            # Normalize composite RRF score to range [0, 1]
            normalized_score = min(1.0, rrf_score / max_possible_rrf) if max_possible_rrf > 0 else 0.0

            payload = point.payload
            scored_candidates.append(
                RetrievedChunkMetadata(
                    chunk_id=str(pid),
                    document_id=payload.get("document_id", ""),
                    file_name=payload.get("file_name", ""),
                    page_or_section=payload.get("page_or_section", "General"),
                    chunk_index=payload.get("chunk_index", 0),
                    text=payload.get("text", ""),
                    score=round(normalized_score, 4),
                    dense_score=round(dense_score, 4) if dense_score > 0 else None,
                    bm25_score=round(bm25_score, 4) if bm25_score > 0 else None,
                )
            )

        # Sort by RRF score descending
        scored_candidates.sort(key=lambda x: x.score, reverse=True)
        return scored_candidates[:limit]


_retriever_instance: Optional[HybridRetriever] = None


def get_retriever() -> HybridRetriever:
    """Return the singleton instance of the HybridRetriever."""
    global _retriever_instance
    if _retriever_instance is None:
        _retriever_instance = HybridRetriever()
    return _retriever_instance
