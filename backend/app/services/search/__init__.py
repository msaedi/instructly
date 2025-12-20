# backend/app/services/search/__init__.py
"""
Natural Language Search services.

This module provides query parsing, embedding, and search functionality
for natural language searches.
"""

from app.services.search.cache_invalidation import (
    invalidate_all_search_cache,
    invalidate_on_availability_change,
    invalidate_on_instructor_profile_change,
    invalidate_on_price_change,
    invalidate_on_review_change,
    invalidate_on_service_change,
)
from app.services.search.circuit_breaker import (
    EMBEDDING_CIRCUIT,
    PARSING_CIRCUIT,
    CircuitBreaker,
    CircuitOpenError,
)
from app.services.search.embedding_provider import (
    EmbeddingProvider,
    MockEmbeddingProvider,
    OpenAIEmbeddingProvider,
    create_embedding_provider,
)
from app.services.search.embedding_service import EmbeddingService
from app.services.search.filter_service import (
    FilteredCandidate,
    FilterResult,
    FilterService,
)
from app.services.search.llm_parser import LLMParser, hybrid_parse
from app.services.search.nl_search_service import NLSearchService
from app.services.search.query_parser import ParsedQuery, QueryParser
from app.services.search.ranking_service import (
    RankedResult,
    RankingResult,
    RankingService,
)
from app.services.search.retriever import (
    PostgresRetriever,
    RetrievalResult,
    Retriever,
    ServiceCandidate,
)
from app.services.search.search_cache import (
    CachedLocation,
    SearchCacheService,
)

__all__ = [
    # Parsing
    "QueryParser",
    "ParsedQuery",
    "LLMParser",
    "hybrid_parse",
    # Circuit breakers
    "PARSING_CIRCUIT",
    "EMBEDDING_CIRCUIT",
    "CircuitOpenError",
    "CircuitBreaker",
    # Embeddings
    "EmbeddingProvider",
    "OpenAIEmbeddingProvider",
    "MockEmbeddingProvider",
    "create_embedding_provider",
    "EmbeddingService",
    # Retrieval
    "PostgresRetriever",
    "Retriever",
    "RetrievalResult",
    "ServiceCandidate",
    # Filtering
    "FilterService",
    "FilterResult",
    "FilteredCandidate",
    # Ranking
    "RankingService",
    "RankedResult",
    "RankingResult",
    # Caching
    "SearchCacheService",
    "CachedLocation",
    "invalidate_on_service_change",
    "invalidate_on_availability_change",
    "invalidate_on_price_change",
    "invalidate_on_instructor_profile_change",
    "invalidate_on_review_change",
    "invalidate_all_search_cache",
    # Main service
    "NLSearchService",
]
