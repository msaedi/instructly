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
import os
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Protocol, Tuple

from app.repositories.retriever_repository import RetrieverRepository
from app.services.search.config import get_search_config
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

# Skip embedding/vector search when trigram text search is already strong enough.
TEXT_SKIP_VECTOR_SCORE_THRESHOLD = float(
    os.getenv("NL_SEARCH_TEXT_SKIP_VECTOR_SCORE_THRESHOLD", "0.60")
)
TEXT_SKIP_VECTOR_MIN_RESULTS = int(os.getenv("NL_SEARCH_TEXT_SKIP_VECTOR_MIN_RESULTS", "10"))

# When trigram returns any strong match for a short, specific query, require lexical support
# (i.e., drop vector-only candidates) to avoid semantic near-misses like "bass guitar" for "violin".
TEXT_REQUIRE_TEXT_MATCH_SCORE_THRESHOLD = float(
    os.getenv("NL_SEARCH_TEXT_REQUIRE_TEXT_MATCH_SCORE_THRESHOLD", "0.45")
)

# Soft budget: if embeddings are slow, fall back to text-only to protect latency.
# When unset/0, we rely on OPENAI_EMBEDDING_TIMEOUT_MS / SearchConfig.embedding_timeout_ms.
_EMBEDDING_SOFT_TIMEOUT_RAW = os.getenv("NL_SEARCH_EMBEDDING_SOFT_TIMEOUT_MS")
EMBEDDING_SOFT_TIMEOUT_MS = (
    int(_EMBEDDING_SOFT_TIMEOUT_RAW) if _EMBEDDING_SOFT_TIMEOUT_RAW is not None else 0
)

# Tokens that commonly appear in many service names and can cause trigram search
# to over-match unrelated categories (e.g., "piano lessons" matching "chess lessons").
TRIGRAM_GENERIC_TOKENS = frozenset({"lesson", "lessons", "class", "classes"})


@dataclass
class ServiceCandidate:
    """
    A service candidate from retrieval with scoring details.

    Represents a bookable instructor service (not just a catalog entry).
    """

    service_id: str  # instructor_service.id
    service_catalog_id: str  # service_catalog.id (for click tracking / schema)
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

    # Timing breakdown (ms) for observability
    embed_latency_ms: int = 0
    db_latency_ms: int = 0
    text_search_latency_ms: int = 0
    vector_search_latency_ms: int = 0


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
        start_total = time.perf_counter()
        embed_latency_ms = 0
        db_latency_ms = 0
        text_latency_ms = 0
        vector_latency_ms = 0

        service_query = parsed_query.service_query

        # Track degradation
        degraded = False
        degradation_reason: Optional[str] = None
        vector_search_used = False

        # Initialize result containers
        vector_results: Dict[str, Tuple[float, ServiceData]] = {}
        text_results: Dict[str, Tuple[float, ServiceData]] = {}

        # Step 1: Always run trigram text search first (fast path for common queries)
        text_query = self._normalize_query_for_trigram(service_query)
        text_start = time.perf_counter()
        text_results = await asyncio.to_thread(
            self._text_search, text_query, text_query, min(TEXT_TOP_K, top_k)
        )
        text_latency_ms = int((time.perf_counter() - text_start) * 1000)

        # If trigram results are strong enough, skip embeddings/vector search entirely.
        best_text_score = max((score for score, _ in text_results.values()), default=0.0)

        # Guardrail: For "specific" service queries (e.g., "violin", "piano lessons"),
        # don't allow unrelated vector-only matches to displace strong lexical matches.
        raw_tokens = [t for t in str(service_query or "").strip().split() if t]
        non_generic_tokens = [t for t in raw_tokens if t.lower() not in TRIGRAM_GENERIC_TOKENS]
        require_text_match = (
            bool(text_results)
            and (0 < len(non_generic_tokens) <= 2)
            and best_text_score >= TEXT_REQUIRE_TEXT_MATCH_SCORE_THRESHOLD
        )

        if (
            len(text_results) >= TEXT_SKIP_VECTOR_MIN_RESULTS
            and best_text_score >= TEXT_SKIP_VECTOR_SCORE_THRESHOLD
        ):
            candidates = self._fuse_scores({}, text_results, top_k)
            db_latency_ms = int((time.perf_counter() - start_total) * 1000)
            return RetrievalResult(
                candidates=candidates,
                total_candidates=len(candidates),
                vector_search_used=False,
                degraded=False,
                degradation_reason=None,
                embed_latency_ms=0,
                db_latency_ms=db_latency_ms,
                text_search_latency_ms=text_latency_ms,
                vector_search_latency_ms=0,
            )

        # Step 2: Only attempt embeddings/vector search when the DB has embeddings.
        embedding_check_start = time.perf_counter()
        has_embeddings = await asyncio.to_thread(self.repository.has_embeddings)
        embedding_check_ms = int((time.perf_counter() - embedding_check_start) * 1000)

        if not has_embeddings:
            logger.warning("No embeddings in database - falling back to text-only search")
            candidates = self._fuse_scores({}, text_results, top_k)
            db_latency_ms = text_latency_ms + embedding_check_ms
            return RetrievalResult(
                candidates=candidates,
                total_candidates=len(candidates),
                vector_search_used=False,
                degraded=True,
                degradation_reason="no_embeddings_in_database",
                embed_latency_ms=0,
                db_latency_ms=db_latency_ms,
                text_search_latency_ms=text_latency_ms,
                vector_search_latency_ms=0,
            )

        # Step 3: Get query embedding (soft time-budgeted for UX)
        embed_start = time.perf_counter()
        try:
            config_timeout_ms = max(0, int(get_search_config().embedding_timeout_ms))
            soft_timeout_ms = max(0, EMBEDDING_SOFT_TIMEOUT_MS)
            timeout_ms = (
                min(config_timeout_ms, soft_timeout_ms) if soft_timeout_ms else config_timeout_ms
            )
            timeout_s = (timeout_ms / 1000.0) if timeout_ms else None

            if timeout_s:
                query_embedding = await asyncio.wait_for(
                    self.embedding_service.embed_query(service_query), timeout=timeout_s
                )
            else:
                query_embedding = await self.embedding_service.embed_query(service_query)
        except asyncio.TimeoutError:
            query_embedding = None
            degraded = True
            degradation_reason = "embedding_timeout"
        embed_latency_ms = int((time.perf_counter() - embed_start) * 1000)

        # Step 4: Run vector search if embedding available, otherwise return text-only.
        if query_embedding:
            vector_start = time.perf_counter()
            vector_results = await asyncio.to_thread(
                self._vector_search, query_embedding, min(VECTOR_TOP_K, top_k)
            )
            vector_latency_ms = int((time.perf_counter() - vector_start) * 1000)
            vector_search_used = True

            if require_text_match and vector_results:
                vector_results = {
                    service_id: entry
                    for service_id, entry in vector_results.items()
                    if service_id in text_results
                }
        else:
            if not degraded:
                logger.warning("Embedding unavailable, using text-only search")
                degraded = True
                degradation_reason = "embedding_service_unavailable"

        # Step 3: Fuse scores
        candidates = self._fuse_scores(vector_results, text_results, top_k)

        db_latency_ms = text_latency_ms + vector_latency_ms + embedding_check_ms
        return RetrievalResult(
            candidates=candidates,
            total_candidates=len(candidates),
            vector_search_used=vector_search_used,
            degraded=degraded,
            degradation_reason=degradation_reason,
            embed_latency_ms=embed_latency_ms,
            db_latency_ms=db_latency_ms,
            text_search_latency_ms=text_latency_ms,
            vector_search_latency_ms=vector_latency_ms,
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
                    "service_catalog_id": row["catalog_id"],
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
                    "service_catalog_id": row["catalog_id"],
                    "name": row["name"],
                    "description": row["description"],
                    "price_per_hour": row["price_per_hour"],
                    "instructor_id": row["instructor_id"],
                },
            )
            for row in rows
        }

    @staticmethod
    def _normalize_query_for_trigram(service_query: str) -> str:
        """
        Reduce trigram over-matching by stripping generic tokens.

        This is intentionally conservative: only removes extremely common tokens.
        Falls back to the original query if stripping would produce an empty query.
        """
        raw = " ".join(str(service_query).strip().split())
        if not raw:
            return ""

        tokens = [t for t in raw.split() if t.lower() not in TRIGRAM_GENERIC_TOKENS]
        normalized = " ".join(tokens).strip()
        return normalized if normalized else raw

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
                    service_catalog_id=str(service_data["service_catalog_id"]),
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
        text_query = self._normalize_query_for_trigram(service_query)
        text_results = await asyncio.to_thread(self._text_search, text_query, text_query, top_k)

        candidates = [
            ServiceCandidate(
                service_id=service_id,
                service_catalog_id=str(data["service_catalog_id"]),
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
