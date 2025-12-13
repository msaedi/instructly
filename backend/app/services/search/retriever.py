# backend/app/services/search/retriever.py
"""
Hybrid candidate retrieval combining vector and trigram search.

This module implements the core search functionality that combines:
- Semantic vector search (pgvector) for meaning-based matching
- Trigram text search (pg_trgm) for typo-tolerant exact matching

Score fusion combines both approaches with configurable weights.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Protocol, Tuple

from app.repositories.retriever_repository import RetrieverRepository
from app.services.search.embedding_service import EmbeddingService

# Type alias for service data dictionary
ServiceData = Dict[str, Any]

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.services.search.query_parser import ParsedQuery

logger = logging.getLogger(__name__)

# Score fusion weights
VECTOR_WEIGHT = 0.6
TEXT_WEIGHT = 0.4
SINGLE_SOURCE_PENALTY = 0.8  # Score multiplier when only in one result set

# Retrieval limits
VECTOR_TOP_K = 30
TEXT_TOP_K = 30
MAX_CANDIDATES = 60


@dataclass
class ServiceCandidate:
    """
    A service candidate from retrieval with scoring details.

    Represents a bookable instructor service (not just a catalog entry).
    """

    service_id: str  # instructor_service.id
    hybrid_score: float  # Combined score (0-1)
    vector_score: Optional[float]  # Semantic similarity (0-1), None if text-only
    text_score: Optional[float]  # Trigram similarity (0-1), None if not matched

    # Service data (eagerly loaded to avoid N+1)
    name: str
    description: Optional[str]
    price_per_hour: int
    instructor_id: str


@dataclass
class RetrievalResult:
    """Result of candidate retrieval."""

    candidates: List[ServiceCandidate]
    total_candidates: int
    vector_search_used: bool  # False if degraded to text-only
    degraded: bool  # True if any degradation occurred
    degradation_reason: Optional[str]


class Retriever(Protocol):
    """Interface for candidate retrievers - enables swapping implementations."""

    async def search(
        self,
        parsed_query: "ParsedQuery",
        top_k: int = MAX_CANDIDATES,
    ) -> RetrievalResult:
        """Retrieve candidate services for a parsed query."""
        ...


class PostgresRetriever:
    """
    Hybrid retriever using PostgreSQL pgvector and pg_trgm.

    Combines semantic vector search with trigram text search for robust results.
    Falls back to text-only search when embedding service is unavailable.

    Usage:
        retriever = PostgresRetriever(db, embedding_service)
        result = await retriever.search(parsed_query)
    """

    def __init__(
        self,
        db: "Session",
        embedding_service: EmbeddingService,
        repository: Optional[RetrieverRepository] = None,
    ) -> None:
        self.db = db
        self.embedding_service = embedding_service
        self.repository = repository or RetrieverRepository(db)

    async def search(
        self,
        parsed_query: "ParsedQuery",
        top_k: int = MAX_CANDIDATES,
    ) -> RetrievalResult:
        """
        Retrieve candidate services using hybrid search.

        1. Check if embeddings exist in database
        2. Generate query embedding (if embeddings exist)
        3. Run vector search (if embedding available)
        4. Run trigram text search
        5. Fuse scores and return top candidates

        Args:
            parsed_query: Parsed query with service_query and original_query
            top_k: Maximum candidates to return

        Returns:
            RetrievalResult with scored candidates
        """
        service_query = parsed_query.service_query
        original_query = parsed_query.original_query

        # Track degradation
        degraded = False
        degradation_reason: Optional[str] = None
        vector_search_used = False

        # Initialize result containers
        vector_results: Dict[str, Tuple[float, ServiceData]] = {}
        text_results: Dict[str, Tuple[float, ServiceData]] = {}

        # Step 0: Check if any embeddings exist in the database
        embedding_count = await asyncio.to_thread(self.repository.count_embeddings)
        if embedding_count == 0:
            logger.warning("No embeddings in database - falling back to text-only search")
            text_results = self._text_search(service_query, original_query, top_k)
            candidates = self._fuse_scores({}, text_results, top_k)
            return RetrievalResult(
                candidates=candidates,
                total_candidates=len(candidates),
                vector_search_used=False,
                degraded=True,
                degradation_reason="no_embeddings_in_database",
            )

        # Step 1: Try to get query embedding
        query_embedding = await self.embedding_service.embed_query(service_query)

        # Step 2: Run searches

        if query_embedding:
            # Run both searches
            vector_results = self._vector_search(query_embedding, VECTOR_TOP_K)
            text_results = self._text_search(service_query, original_query, TEXT_TOP_K)
            vector_search_used = True
        else:
            # Degraded mode: text-only search
            logger.warning("Embedding unavailable, using text-only search")
            text_results = self._text_search(service_query, original_query, top_k)
            degraded = True
            degradation_reason = "embedding_service_unavailable"

        # Step 3: Fuse scores
        candidates = self._fuse_scores(vector_results, text_results, top_k)

        return RetrievalResult(
            candidates=candidates,
            total_candidates=len(candidates),
            vector_search_used=vector_search_used,
            degraded=degraded,
            degradation_reason=degradation_reason,
        )

    def _vector_search(
        self,
        query_embedding: List[float],
        top_k: int,
    ) -> Dict[str, Tuple[float, ServiceData]]:
        """
        Run semantic vector similarity search using pgvector.

        Returns dict mapping service_id to (score, service_data).
        """
        rows = self.repository.vector_search(query_embedding, top_k)

        return {
            str(row["id"]): (
                float(row["vector_score"]),
                {
                    "name": row["name"],
                    "description": row["description"],
                    "price_per_hour": row["price_per_hour"],
                    "instructor_id": row["instructor_id"],
                },
            )
            for row in rows
        }

    def _text_search(
        self,
        corrected_query: str,
        original_query: str,
        top_k: int,
    ) -> Dict[str, Tuple[float, ServiceData]]:
        """
        Run trigram text similarity search using pg_trgm.

        Returns dict mapping service_id to (score, service_data).
        """
        rows = self.repository.text_search(corrected_query, original_query, top_k)

        return {
            str(row["id"]): (
                float(row["text_score"]),
                {
                    "name": row["name"],
                    "description": row["description"],
                    "price_per_hour": row["price_per_hour"],
                    "instructor_id": row["instructor_id"],
                },
            )
            for row in rows
        }

    def _fuse_scores(
        self,
        vector_results: Dict[str, Tuple[float, ServiceData]],
        text_results: Dict[str, Tuple[float, ServiceData]],
        top_k: int,
    ) -> List[ServiceCandidate]:
        """
        Fuse vector and text search scores into hybrid score.

        Score fusion strategy:
        - Services in both: hybrid = (0.6 * vector) + (0.4 * text)
        - Services in one: hybrid = single_score * 0.8
        """
        # Collect all unique service IDs
        all_service_ids = set(vector_results.keys()) | set(text_results.keys())

        candidates = []
        for service_id in all_service_ids:
            vector_entry = vector_results.get(service_id)
            text_entry = text_results.get(service_id)

            vector_score = vector_entry[0] if vector_entry else None
            text_score = text_entry[0] if text_entry else None

            # Get service data from whichever result has it
            # At least one must exist since service_id is in the union of both result sets
            if vector_entry is not None:
                service_data = vector_entry[1]
            elif text_entry is not None:
                service_data = text_entry[1]
            else:
                # Should never happen - skip this service_id
                continue

            # Calculate hybrid score
            if vector_score is not None and text_score is not None:
                # Both sources - weighted combination
                hybrid_score = (VECTOR_WEIGHT * vector_score) + (TEXT_WEIGHT * text_score)
            elif vector_score is not None:
                # Vector only - apply penalty
                hybrid_score = vector_score * SINGLE_SOURCE_PENALTY
            else:
                # Text only - apply penalty (text_score guaranteed non-None here)
                hybrid_score = (text_score or 0.0) * SINGLE_SOURCE_PENALTY

            candidates.append(
                ServiceCandidate(
                    service_id=service_id,
                    hybrid_score=hybrid_score,
                    vector_score=vector_score,
                    text_score=text_score,
                    name=str(service_data["name"]),
                    description=str(service_data["description"])
                    if service_data["description"]
                    else None,
                    price_per_hour=int(service_data["price_per_hour"]),
                    instructor_id=str(service_data["instructor_id"]),
                )
            )

        # Sort by hybrid score descending
        candidates.sort(key=lambda c: c.hybrid_score, reverse=True)

        # Return top K
        return candidates[:top_k]

    async def text_only_search(
        self,
        service_query: str,
        original_query: str,
        top_k: int = MAX_CANDIDATES,
    ) -> RetrievalResult:
        """
        Text-only search for explicit degraded mode.

        Useful when you know embedding service is down and want to skip the check.

        Args:
            service_query: Corrected service query
            original_query: Original user query
            top_k: Maximum candidates to return

        Returns:
            RetrievalResult with text-only candidates
        """
        text_results = self._text_search(service_query, original_query, top_k)

        candidates = [
            ServiceCandidate(
                service_id=service_id,
                hybrid_score=score * SINGLE_SOURCE_PENALTY,
                vector_score=None,
                text_score=score,
                name=str(data["name"]),
                description=str(data["description"]) if data["description"] else None,
                price_per_hour=int(data["price_per_hour"]),
                instructor_id=str(data["instructor_id"]),
            )
            for service_id, (score, data) in text_results.items()
        ]

        candidates.sort(key=lambda c: c.hybrid_score, reverse=True)

        return RetrievalResult(
            candidates=candidates[:top_k],
            total_candidates=len(candidates),
            vector_search_used=False,
            degraded=True,
            degradation_reason="text_only_mode",
        )
