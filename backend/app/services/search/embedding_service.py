# backend/app/services/search/embedding_service.py
"""
Embedding service for semantic search.
Handles query embedding (search-time) and service embedding (index-time).
"""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, cast
import uuid
import weakref

from app.repositories.service_catalog_repository import ServiceCatalogRepository
from app.services.cache_service import CacheService, CircuitState
from app.services.search.circuit_breaker import EMBEDDING_CIRCUIT, CircuitOpenError
from app.services.search.config import get_search_config
from app.services.search.embedding_provider import (
    EmbeddingProvider,
    create_embedding_provider,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.services.cache_service import CacheService

logger = logging.getLogger(__name__)

# Configuration
EMBEDDING_CACHE_TTL = 60 * 60 * 24  # 24 hours

_SINGLEFLIGHT_LOCK_TTL_S = 30
_SINGLEFLIGHT_POLL_INTERVAL_S = 0.5
_SINGLEFLIGHT_POLL_TIMEOUT_S = 30.0
_SINGLEFLIGHT_RELEASE_LOCK_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
  return redis.call("del", KEYS[1])
end
return 0
"""

_pending_by_loop: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, Dict[str, asyncio.Future[Optional[List[float]]]]]" = (
    weakref.WeakKeyDictionary()
)
_locks_by_loop: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock]" = (
    weakref.WeakKeyDictionary()
)


def _get_current_model() -> str:
    """Get the current embedding model from config."""
    return get_search_config().embedding_model


class EmbeddingService:
    """
    Service for generating and managing embeddings.

    Responsibilities:
    - Query embedding (search-time, cached)
    - Service embedding (index-time)
    - Embedding text generation for services
    - Cache management
    """

    def __init__(
        self,
        cache_service: Optional["CacheService"] = None,
        provider: Optional[EmbeddingProvider] = None,
    ) -> None:
        self.cache = cache_service
        self._provider = provider

    @property
    def provider(self) -> EmbeddingProvider:
        """Lazy initialization of embedding provider."""
        if self._provider is None:
            self._provider = create_embedding_provider()
        return self._provider

    # =========================================================================
    # Query Embedding (Search-Time)
    # =========================================================================

    async def embed_query(self, query: str) -> Optional[List[float]]:
        """
        Generate embedding for a search query.

        - Checks cache first
        - Falls back to None if circuit is open (enables text-only search)

        Args:
            query: The search query text

        Returns:
            Embedding vector or None if unavailable
        """
        # Normalize query
        normalized = query.lower().strip()

        # Check cache
        cache_key = self._query_cache_key(normalized)
        if self.cache:
            cached = await self.cache.get(cache_key)
            if cached is not None and isinstance(cached, list):
                logger.debug(f"Embedding cache hit for: {normalized[:50]}")
                return cast(List[float], cached)

        # Check circuit breaker
        if EMBEDDING_CIRCUIT.is_open:
            logger.warning("Embedding circuit is OPEN, returning None")
            return None

        pending_future: Optional[asyncio.Future[Optional[List[float]]]] = None
        pending_lock: Optional[asyncio.Lock] = None
        is_owner = False

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None:
            pending = _pending_by_loop.get(loop)
            if pending is None:
                pending = {}
                _pending_by_loop[loop] = pending

            pending_lock = _locks_by_loop.get(loop)
            if pending_lock is None:
                pending_lock = asyncio.Lock()
                _locks_by_loop[loop] = pending_lock

            async with pending_lock:
                existing = pending.get(cache_key)
                if existing is not None:
                    pending_future = existing
                else:
                    pending_future = loop.create_future()
                    pending[cache_key] = pending_future
                    is_owner = True

            if not is_owner:
                if pending_future is None:
                    raise RuntimeError("Pending future missing for embedding coalescing")
                logger.info("[EMBED] Coalesced request for: %s", normalized[:50])
                return await pending_future

        embedding: Optional[List[float]] = None
        try:
            redis_client = None
            if isinstance(self.cache, CacheService):
                if self.cache.circuit_breaker.state != CircuitState.OPEN:
                    redis_client = await self.cache.get_redis_client()

            if redis_client is not None:
                computing_key = f"{cache_key}:computing"
                token = uuid.uuid4().hex
                acquired = False

                try:
                    acquired = bool(
                        await redis_client.set(
                            computing_key,
                            token,
                            nx=True,
                            ex=_SINGLEFLIGHT_LOCK_TTL_S,
                        )
                    )
                except Exception as lock_error:
                    logger.warning(f"[EMBED] Redis singleflight lock failed: {lock_error}")

                if acquired:
                    logger.info("[EMBED] Leader for: %s", normalized[:50])
                    try:
                        try:
                            embedding = await EMBEDDING_CIRCUIT.call(
                                self.provider.embed, normalized
                            )
                        except CircuitOpenError:
                            logger.warning("Embedding circuit opened during call")
                            embedding = None
                        except Exception as e:
                            # Don't record_failure here - CircuitBreaker.call() already did
                            logger.error(f"Embedding generation failed: {e}")
                            embedding = None

                        if embedding is not None and self.cache:
                            try:
                                await self.cache.set(
                                    cache_key,
                                    embedding,
                                    ttl=EMBEDDING_CACHE_TTL,
                                )
                            except Exception as cache_error:
                                logger.warning(f"Failed to cache embedding: {cache_error}")

                        return embedding
                    finally:
                        with contextlib.suppress(Exception):
                            await redis_client.eval(
                                _SINGLEFLIGHT_RELEASE_LOCK_LUA,
                                1,
                                computing_key,
                                token,
                            )
                else:
                    logger.info("[EMBED] Waiting for leader: %s", normalized[:50])
                    if self.cache:
                        cached = await self.cache.get(cache_key)
                        if cached is not None and isinstance(cached, list):
                            embedding = cast(List[float], cached)
                            return embedding

                    poll_attempts = int(
                        _SINGLEFLIGHT_POLL_TIMEOUT_S / _SINGLEFLIGHT_POLL_INTERVAL_S
                    )
                    for _ in range(max(1, poll_attempts)):
                        await asyncio.sleep(_SINGLEFLIGHT_POLL_INTERVAL_S)
                        if self.cache:
                            cached = await self.cache.get(cache_key)
                            if cached is not None and isinstance(cached, list):
                                embedding = cast(List[float], cached)
                                return embedding
                        with contextlib.suppress(Exception):
                            if not await redis_client.exists(computing_key):
                                break
                    if self.cache:
                        cached = await self.cache.get(cache_key)
                        if cached is not None and isinstance(cached, list):
                            logger.debug(
                                "[EMBED] Cache hit after leader released lock: %s", normalized[:50]
                            )
                            embedding = cast(List[float], cached)
                            return embedding

            try:
                embedding = await EMBEDDING_CIRCUIT.call(self.provider.embed, normalized)
            except CircuitOpenError:
                logger.warning("Embedding circuit opened during call")
                embedding = None
            except Exception as e:
                # Don't record_failure here - CircuitBreaker.call() already did
                logger.error(f"Embedding generation failed: {e}")
                embedding = None

            if embedding is not None and self.cache:
                try:
                    await self.cache.set(cache_key, embedding, ttl=EMBEDDING_CACHE_TTL)
                except Exception as cache_error:
                    logger.warning(f"Failed to cache embedding: {cache_error}")

            return embedding
        finally:
            if loop is not None and pending_future is not None and is_owner:
                if not pending_future.done():
                    pending_future.set_result(embedding)
                pending = _pending_by_loop.get(loop)
                if pending is not None:
                    pending.pop(cache_key, None)

    def _query_cache_key(self, normalized_query: str) -> str:
        """Generate cache key for query embedding."""
        model_name = self.provider.get_model_name()
        query_hash = hashlib.sha256(normalized_query.encode()).hexdigest()[:16]
        return f"embed:{model_name}:{query_hash}"

    # =========================================================================
    # Service Embedding (Index-Time)
    # =========================================================================

    def generate_embedding_text(self, service: Any) -> str:
        """
        Generate the text to embed for a service.

        Concatenates relevant fields for rich semantic representation.
        """
        parts = [service.name]

        if service.description:
            parts.append(service.description)

        # Add category if available
        if hasattr(service, "category") and service.category:
            category_name = getattr(service.category, "name", None)
            if category_name:
                parts.append(f"Category: {category_name}")
        elif hasattr(service, "category_name") and service.category_name:
            parts.append(f"Category: {service.category_name}")

        # Add audience if available
        if hasattr(service, "audience") and service.audience:
            parts.append(f"Audience: {service.audience}")

        # Add skill levels if available
        if hasattr(service, "skill_levels") and service.skill_levels:
            parts.append(f"Skill levels: {', '.join(service.skill_levels)}")

        return ". ".join(parts)

    def compute_text_hash(self, text: str) -> str:
        """Compute hash of embedding text for change detection."""
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def needs_reembedding(self, service: Any) -> bool:
        """
        Check if service needs new embedding.

        Returns True if:
        1. No embedding exists (embedding_v2 is None)
        2. Model has changed
        3. Service content has changed (text hash mismatch)
        """
        # 1. No embedding exists
        if service.embedding_v2 is None:
            return True

        # 2. Model has changed
        if service.embedding_model != _get_current_model():
            return True

        # 3. Content has changed
        current_text = self.generate_embedding_text(service)
        current_hash = self.compute_text_hash(current_text)
        if service.embedding_text_hash != current_hash:
            return True

        return False

    async def embed_service(self, service: Any) -> Optional[List[float]]:
        """
        Generate embedding for a service.

        Used when creating/updating services and during migration.
        Does NOT update the database - caller is responsible for that.

        Returns:
            Embedding vector or None if generation failed
        """
        text = self.generate_embedding_text(service)

        try:
            embedding = await EMBEDDING_CIRCUIT.call(self.provider.embed, text)
            return embedding
        except Exception as e:
            logger.error(f"Failed to embed service {service.id}: {e}")
            return None

    async def embed_services_batch(
        self, services: List[Any], batch_size: int = 50
    ) -> Dict[str, List[float]]:
        """
        Generate embeddings for multiple services efficiently.

        Uses batch API for better throughput.

        Args:
            services: List of service objects
            batch_size: Number of services per API call

        Returns:
            Dict mapping service_id to embedding
        """
        results: Dict[str, List[float]] = {}

        for i in range(0, len(services), batch_size):
            batch = services[i : i + batch_size]
            texts = [self.generate_embedding_text(s) for s in batch]

            try:
                embeddings = await EMBEDDING_CIRCUIT.call(self.provider.embed_batch, texts)

                for service, embedding in zip(batch, embeddings):
                    results[service.id] = embedding

            except Exception as e:
                logger.error(f"Batch embedding failed: {e}")
                # Try individual embedding as fallback
                for service in batch:
                    emb = await self.embed_service(service)
                    if emb:
                        results[service.id] = emb

        return results

    # =========================================================================
    # Migration Support
    # =========================================================================

    def get_services_needing_embedding(self, db: "Session", limit: int = 100) -> List[Any]:
        """
        Find services that need embedding generation or update.

        Queries for:
        - Services with NULL embedding_v2
        - Services with different embedding_model than current
        - Services with stale embeddings (>30 days old)
        """
        return ServiceCatalogRepository(db).get_services_needing_embedding(
            _get_current_model(), limit
        )

    def update_service_embedding(
        self, db: "Session", service_id: str, embedding: List[float], text_hash: str
    ) -> bool:
        """
        Update a service's embedding in the database.

        Updates embedding_v2 and metadata columns.
        """
        return ServiceCatalogRepository(db).update_service_embedding(
            service_id, embedding, _get_current_model(), text_hash
        )
