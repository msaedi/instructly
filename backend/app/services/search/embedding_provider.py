# backend/app/services/search/embedding_provider.py
"""
Embedding provider abstraction for semantic search.
Supports OpenAI (production) and mock (testing) providers.
Uses strict timeouts to fail fast under load (no retries).
"""
from __future__ import annotations

import hashlib
import logging
import os
import random
from typing import List, Optional, Protocol

from openai import AsyncOpenAI

from app.services.search.config import get_search_config

logger = logging.getLogger(__name__)

# Strict OpenAI timeouts for async embedding calls.
# Fail fast rather than block for 5+ seconds with retries.
OPENAI_TIMEOUT_S = float(os.getenv("OPENAI_TIMEOUT_S", "2.0"))


class EmbeddingProvider(Protocol):
    """Interface for embedding providers - enables easy swapping."""

    async def embed(self, text: str) -> List[float]:
        """Generate embedding vector for text."""
        ...

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts (more efficient)."""
        ...

    def get_model_name(self) -> str:
        """Return the model name for tracking."""
        ...

    def get_dimensions(self) -> int:
        """Return the embedding dimensions."""
        ...


class OpenAIEmbeddingProvider:
    """
    Production embedding provider using OpenAI API.

    IMPORTANT: Uses AsyncOpenAI for FastAPI async compatibility.
    """

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        dimensions: int = 1536,
    ) -> None:
        self.model = model
        self.dimensions = dimensions
        self._client: Optional[AsyncOpenAI] = None
        self._client_max_retries: Optional[int] = None

    @property
    def client(self) -> AsyncOpenAI:
        """Lazy initialization of OpenAI client with strict timeouts."""
        max_retries = int(get_search_config().max_retries)
        if self._client is None or self._client_max_retries != max_retries:
            self._client = AsyncOpenAI(
                timeout=OPENAI_TIMEOUT_S,
                max_retries=max_retries,
            )
            self._client_max_retries = max_retries
        return self._client

    async def embed(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        response = await self.client.embeddings.create(
            model=self.model,
            input=text,
            dimensions=self.dimensions,
        )
        return list(response.data[0].embedding)

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in a single API call.

        More efficient than calling embed() multiple times.
        Max batch size is ~8000 tokens total.
        """
        if not texts:
            return []

        response = await self.client.embeddings.create(
            model=self.model,
            input=texts,
            dimensions=self.dimensions,
        )

        # Return in same order as input
        sorted_data = sorted(response.data, key=lambda x: x.index)
        return [list(item.embedding) for item in sorted_data]

    def get_model_name(self) -> str:
        return self.model

    def get_dimensions(self) -> int:
        return self.dimensions


class MockEmbeddingProvider:
    """
    Deterministic mock embeddings for testing.

    Properties:
    - Same input always produces same output (deterministic)
    - Different inputs produce different outputs (distinguishable)
    - Output is valid embedding format (normalized unit vector)

    Use for:
    - Unit tests (fast, no API calls)
    - Load testing (avoid rate limits)
    - CI pipelines (no external dependency)
    """

    def __init__(self, dimensions: int = 1536) -> None:
        self.dimensions = dimensions

    async def embed(self, text: str) -> List[float]:
        """Generate deterministic mock embedding."""
        return self._generate_embedding(text)

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate mock embeddings for multiple texts."""
        return [self._generate_embedding(text) for text in texts]

    def _generate_embedding(self, text: str) -> List[float]:
        """Create deterministic embedding from text hash."""
        # Create deterministic seed from text
        text_hash = hashlib.sha256(text.lower().encode()).hexdigest()
        seed = int(text_hash[:8], 16)

        # Generate deterministic "embedding"
        rng = random.Random(seed)
        embedding = [rng.gauss(0, 1) for _ in range(self.dimensions)]

        # Normalize to unit length (like real embeddings)
        magnitude = sum(x**2 for x in embedding) ** 0.5
        return [x / magnitude for x in embedding]

    def get_model_name(self) -> str:
        return "mock-embedding-v1"

    def get_dimensions(self) -> int:
        return self.dimensions


def create_embedding_provider(model: Optional[str] = None) -> EmbeddingProvider:
    """
    Factory function to create the appropriate embedding provider.

    Args:
        model: Optional model override. If None, uses config or environment.

    Environment Variables:
    - EMBEDDING_PROVIDER: "openai" (default) or "mock"
    - OPENAI_EMBEDDING_MODEL: Model name (default: "text-embedding-3-small")
    - EMBEDDING_DIMENSIONS: Vector dimensions (default: 1536)
    """
    from app.services.search.config import get_search_config

    provider = os.getenv("EMBEDDING_PROVIDER", "openai")
    dimensions = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))

    if provider == "mock":
        logger.info("Using mock embedding provider")
        return MockEmbeddingProvider(dimensions=dimensions)
    else:
        # Use provided model, config, or fall back to env
        if model is None:
            config = get_search_config()
            model = config.embedding_model
        logger.info(f"Using OpenAI embedding provider: {model}")
        return OpenAIEmbeddingProvider(model=model, dimensions=dimensions)
