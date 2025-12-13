# backend/app/services/search/__init__.py
"""
Natural Language Search services.

This module provides query parsing, embedding, and search functionality
for natural language searches.
"""

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
from app.services.search.query_parser import ParsedQuery, QueryParser
from app.services.search.retriever import (
    PostgresRetriever,
    RetrievalResult,
    Retriever,
    ServiceCandidate,
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
]
