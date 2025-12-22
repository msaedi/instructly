# backend/tests/unit/services/search/test_embedding_service.py
"""
Unit tests for embedding service.
Uses mock provider to avoid API calls.
"""
from __future__ import annotations

import asyncio
import threading
import time
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.services.cache_service import CacheService
from app.services.search.circuit_breaker import EMBEDDING_CIRCUIT
from app.services.search.config import get_search_config
from app.services.search.embedding_provider import (
    MockEmbeddingProvider,
    OpenAIEmbeddingProvider,
    create_embedding_provider,
)
from app.services.search.embedding_service import EmbeddingService


@pytest.fixture
def mock_cache() -> AsyncMock:
    """Create mock async cache service."""
    cache = AsyncMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock(return_value=True)
    return cache


@pytest.fixture
def mock_provider() -> MockEmbeddingProvider:
    """Create mock embedding provider."""
    return MockEmbeddingProvider(dimensions=1536)


@pytest.fixture
def embedding_service(
    mock_cache: Mock, mock_provider: MockEmbeddingProvider
) -> EmbeddingService:
    """Create embedding service with mocks."""
    service = EmbeddingService(cache_service=mock_cache, provider=mock_provider)
    return service


@pytest.fixture(autouse=True)
def reset_circuit() -> Any:
    """Reset circuit breaker before each test."""
    EMBEDDING_CIRCUIT.reset()
    yield
    EMBEDDING_CIRCUIT.reset()


class TestMockEmbeddingProvider:
    """Tests for mock embedding provider."""

    @pytest.mark.asyncio
    async def test_deterministic_output(self, mock_provider: MockEmbeddingProvider) -> None:
        """Same input should produce same output."""
        text = "piano lessons"

        emb1 = await mock_provider.embed(text)
        emb2 = await mock_provider.embed(text)

        assert emb1 == emb2

    @pytest.mark.asyncio
    async def test_different_inputs_different_outputs(
        self, mock_provider: MockEmbeddingProvider
    ) -> None:
        """Different inputs should produce different outputs."""
        emb1 = await mock_provider.embed("piano lessons")
        emb2 = await mock_provider.embed("guitar lessons")

        assert emb1 != emb2

    @pytest.mark.asyncio
    async def test_normalized_output(self, mock_provider: MockEmbeddingProvider) -> None:
        """Output should be unit vector (normalized)."""
        emb = await mock_provider.embed("test")

        magnitude = sum(x**2 for x in emb) ** 0.5
        assert abs(magnitude - 1.0) < 0.0001

    @pytest.mark.asyncio
    async def test_correct_dimensions(self, mock_provider: MockEmbeddingProvider) -> None:
        """Output should have correct dimensions."""
        emb = await mock_provider.embed("test")

        assert len(emb) == 1536

    @pytest.mark.asyncio
    async def test_batch_embedding(self, mock_provider: MockEmbeddingProvider) -> None:
        """Batch embedding should work correctly."""
        texts = ["piano", "guitar", "violin"]

        embeddings = await mock_provider.embed_batch(texts)

        assert len(embeddings) == 3
        assert all(len(e) == 1536 for e in embeddings)

    def test_get_model_name(self, mock_provider: MockEmbeddingProvider) -> None:
        """Should return mock model name."""
        assert mock_provider.get_model_name() == "mock-embedding-v1"

    def test_get_dimensions(self, mock_provider: MockEmbeddingProvider) -> None:
        """Should return configured dimensions."""
        assert mock_provider.get_dimensions() == 1536


class TestEmbeddingService:
    """Tests for embedding service."""

    @pytest.mark.asyncio
    async def test_embed_query_returns_vector(
        self, embedding_service: EmbeddingService
    ) -> None:
        """Query embedding should return vector."""
        result = await embedding_service.embed_query("piano lessons")

        assert result is not None
        assert len(result) == 1536

    @pytest.mark.asyncio
    async def test_embed_query_uses_cache(
        self, embedding_service: EmbeddingService, mock_cache: AsyncMock
    ) -> None:
        """Should check cache before generating."""
        cached_embedding = [0.1] * 1536
        mock_cache.get.return_value = cached_embedding

        result = await embedding_service.embed_query("piano lessons")

        assert result == cached_embedding
        mock_cache.get.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_embed_query_caches_result(
        self, embedding_service: EmbeddingService, mock_cache: AsyncMock
    ) -> None:
        """Should cache generated embeddings."""
        mock_cache.get.return_value = None

        await embedding_service.embed_query("piano lessons")

        mock_cache.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_embed_query_returns_none_when_circuit_open(
        self, embedding_service: EmbeddingService
    ) -> None:
        """Should return None when circuit is open."""
        # Open the circuit
        for _ in range(5):
            EMBEDDING_CIRCUIT._record_failure()

        result = await embedding_service.embed_query("piano lessons")

        assert result is None

    @pytest.mark.asyncio
    async def test_normalizes_query(self, embedding_service: EmbeddingService) -> None:
        """Should normalize query before embedding."""
        result1 = await embedding_service.embed_query("PIANO LESSONS")
        result2 = await embedding_service.embed_query("piano lessons")

        # Mock provider is deterministic, so normalized queries should match
        assert result1 == result2

    @pytest.mark.asyncio
    async def test_embed_query_coalesces_concurrent_requests(
        self, mock_cache: AsyncMock
    ) -> None:
        """Concurrent identical queries should share a single provider call."""

        class SlowCountingProvider(MockEmbeddingProvider):
            def __init__(self) -> None:
                super().__init__(dimensions=1536)
                self.calls = 0

            async def embed(self, text: str) -> list[float]:
                self.calls += 1
                await asyncio.sleep(0.05)
                return await super().embed(text)

        provider = SlowCountingProvider()
        service_a = EmbeddingService(cache_service=mock_cache, provider=provider)
        service_b = EmbeddingService(cache_service=mock_cache, provider=provider)

        results = await asyncio.gather(
            service_a.embed_query("PIANO LESSONS"),
            service_b.embed_query("  piano lessons  "),
        )

        assert provider.calls == 1
        assert results[0] == results[1]

    @pytest.mark.asyncio
    async def test_embed_query_coalesces_failures(
        self, mock_cache: AsyncMock
    ) -> None:
        """If the shared call fails, all waiters should return None (no hang)."""

        class FailingProvider(MockEmbeddingProvider):
            def __init__(self) -> None:
                super().__init__(dimensions=1536)
                self.calls = 0

            async def embed(self, text: str) -> list[float]:
                self.calls += 1
                await asyncio.sleep(0.05)
                raise RuntimeError("boom")

        provider = FailingProvider()
        service_a = EmbeddingService(cache_service=mock_cache, provider=provider)
        service_b = EmbeddingService(cache_service=mock_cache, provider=provider)

        results = await asyncio.gather(
            service_a.embed_query("piano lessons"),
            service_b.embed_query("piano lessons"),
        )

        assert provider.calls == 1
        assert results == [None, None]

    @pytest.mark.asyncio
    async def test_embed_query_cross_worker_singleflight(
        self,
    ) -> None:
        """Identical queries on different event loops should share one provider call via Redis."""

        class FakeAsyncRedis:
            def __init__(self) -> None:
                self._lock = threading.Lock()
                self._data: dict[str, str] = {}
                self._expires_at: dict[str, float] = {}

            def _purge_expired(self) -> None:
                now = time.monotonic()
                expired = [k for k, exp in self._expires_at.items() if exp <= now]
                for k in expired:
                    self._data.pop(k, None)
                    self._expires_at.pop(k, None)

            async def get(self, key: str) -> str | None:
                with self._lock:
                    self._purge_expired()
                    return self._data.get(key)

            async def setex(self, key: str, ttl: int, value: str) -> bool:
                with self._lock:
                    self._purge_expired()
                    self._data[key] = value
                    self._expires_at[key] = time.monotonic() + ttl
                    return True

            async def set(
                self, key: str, value: str, *, nx: bool = False, ex: int | None = None
            ) -> bool | None:
                with self._lock:
                    self._purge_expired()
                    if nx and key in self._data:
                        return None
                    self._data[key] = value
                    if ex is not None:
                        self._expires_at[key] = time.monotonic() + ex
                    else:
                        self._expires_at.pop(key, None)
                    return True

            async def exists(self, key: str) -> int:
                with self._lock:
                    self._purge_expired()
                    return 1 if key in self._data else 0

            async def eval(self, script: str, numkeys: int, key: str, token: str) -> int:
                with self._lock:
                    self._purge_expired()
                    if self._data.get(key) != token:
                        return 0
                    self._data.pop(key, None)
                    self._expires_at.pop(key, None)
                    return 1

        class SlowThreadSafeProvider(MockEmbeddingProvider):
            def __init__(self) -> None:
                super().__init__(dimensions=1536)
                self._calls = 0
                self._calls_lock = threading.Lock()

            @property
            def calls(self) -> int:
                with self._calls_lock:
                    return self._calls

            async def embed(self, text: str) -> list[float]:
                with self._calls_lock:
                    self._calls += 1
                await asyncio.sleep(0.05)  # Reduced from 0.2 for faster tests
                return await super().embed(text)

        def _run_in_new_loop(coro: Any) -> Any:
            return asyncio.run(coro)

        redis = FakeAsyncRedis()
        provider = SlowThreadSafeProvider()

        with patch.dict("os.environ", {"AVAILABILITY_TEST_MEMORY_CACHE": "0"}):
            cache_a = CacheService(db=None, redis_client=redis)  # type: ignore[arg-type]
            cache_b = CacheService(db=None, redis_client=redis)  # type: ignore[arg-type]
            service_a = EmbeddingService(cache_service=cache_a, provider=provider)
            service_b = EmbeddingService(cache_service=cache_b, provider=provider)

            results = await asyncio.gather(
                asyncio.to_thread(_run_in_new_loop, service_a.embed_query("piano lessons")),
                asyncio.to_thread(_run_in_new_loop, service_b.embed_query("piano lessons")),
            )

        assert provider.calls == 1
        assert results[0] == results[1]


class TestEmbeddingTextGeneration:
    """Tests for service embedding text generation."""

    def test_basic_text_generation(self, embedding_service: EmbeddingService) -> None:
        """Should generate text from service name and description."""
        service = Mock()
        service.name = "Piano Lessons"
        service.description = "Learn piano basics"
        service.category = None

        # Remove optional attributes to avoid hasattr returning True
        type(service).audience = property(lambda self: None)
        type(service).skill_levels = property(lambda self: None)

        text = embedding_service.generate_embedding_text(service)

        assert "Piano Lessons" in text
        assert "Learn piano basics" in text

    def test_includes_category(self, embedding_service: EmbeddingService) -> None:
        """Should include category in embedding text."""
        service = Mock()
        service.name = "Piano Lessons"
        service.description = "Learn piano"
        service.category = Mock()
        service.category.name = "Music"

        # Remove optional attributes
        type(service).audience = property(lambda self: None)
        type(service).skill_levels = property(lambda self: None)

        text = embedding_service.generate_embedding_text(service)

        assert "Category: Music" in text

    def test_includes_audience(self, embedding_service: EmbeddingService) -> None:
        """Should include audience in embedding text."""
        service = Mock()
        service.name = "Piano for Kids"
        service.description = "Fun lessons"
        service.category = None
        service.audience = "kids"

        # Remove optional attributes
        type(service).skill_levels = property(lambda self: None)

        text = embedding_service.generate_embedding_text(service)

        assert "Audience: kids" in text

    def test_includes_skill_levels(self, embedding_service: EmbeddingService) -> None:
        """Should include skill levels in embedding text."""
        service = Mock()
        service.name = "Piano Lessons"
        service.description = "All levels"
        service.category = None
        service.skill_levels = ["beginner", "intermediate"]

        # Remove optional attributes
        type(service).audience = property(lambda self: None)

        text = embedding_service.generate_embedding_text(service)

        assert "Skill levels: beginner, intermediate" in text


class TestNeedsReembedding:
    """Tests for re-embedding detection."""

    def test_needs_reembedding_when_no_embedding(
        self, embedding_service: EmbeddingService
    ) -> None:
        """Should return True when embedding_v2 is None."""
        service = Mock()
        service.embedding_v2 = None

        assert embedding_service.needs_reembedding(service) is True

    def test_needs_reembedding_when_model_changed(
        self, embedding_service: EmbeddingService
    ) -> None:
        """Should return True when model has changed."""
        service = Mock()
        service.embedding_v2 = [0.1] * 1536
        service.embedding_model = "old-model"

        assert embedding_service.needs_reembedding(service) is True

    def test_needs_reembedding_when_content_changed(
        self, embedding_service: EmbeddingService
    ) -> None:
        """Should return True when service content changed."""
        service = Mock()
        service.embedding_v2 = [0.1] * 1536
        service.embedding_model = get_search_config().embedding_model
        service.embedding_text_hash = "old_hash"
        service.name = "Updated Name"
        service.description = "New description"
        service.category = None

        # Remove optional attributes
        type(service).audience = property(lambda self: None)
        type(service).skill_levels = property(lambda self: None)

        assert embedding_service.needs_reembedding(service) is True

    def test_no_reembedding_when_current(
        self, embedding_service: EmbeddingService
    ) -> None:
        """Should return False when embedding is current."""
        service = Mock()
        service.embedding_v2 = [0.1] * 1536
        service.embedding_model = get_search_config().embedding_model
        service.name = "Piano Lessons"
        service.description = "Learn piano"
        service.category = None

        # Remove optional attributes
        type(service).audience = property(lambda self: None)
        type(service).skill_levels = property(lambda self: None)

        # Compute current hash
        text = embedding_service.generate_embedding_text(service)
        service.embedding_text_hash = embedding_service.compute_text_hash(text)

        assert embedding_service.needs_reembedding(service) is False


class TestCreateEmbeddingProvider:
    """Tests for provider factory."""

    def test_creates_mock_provider(self) -> None:
        """Should create mock provider when configured."""
        with patch.dict("os.environ", {"EMBEDDING_PROVIDER": "mock"}):
            provider = create_embedding_provider()
            assert isinstance(provider, MockEmbeddingProvider)

    def test_creates_openai_provider_by_default(self) -> None:
        """Should create OpenAI provider by default."""
        with patch.dict(
            "os.environ", {"EMBEDDING_PROVIDER": "openai"}, clear=False
        ):
            provider = create_embedding_provider()
            assert isinstance(provider, OpenAIEmbeddingProvider)

    def test_respects_dimensions_config(self) -> None:
        """Should use configured dimensions."""
        with patch.dict(
            "os.environ",
            {"EMBEDDING_PROVIDER": "mock", "EMBEDDING_DIMENSIONS": "768"},
        ):
            provider = create_embedding_provider()
            assert provider.get_dimensions() == 768


class TestBatchEmbedding:
    """Tests for batch embedding operations."""

    @pytest.mark.asyncio
    async def test_embed_services_batch(
        self, embedding_service: EmbeddingService
    ) -> None:
        """Should embed multiple services in a batch."""
        services = []
        for i in range(3):
            svc = Mock()
            svc.id = f"svc_{i}"
            svc.name = f"Service {i}"
            svc.description = f"Description {i}"
            svc.category = None
            type(svc).audience = property(lambda self: None)
            type(svc).skill_levels = property(lambda self: None)
            services.append(svc)

        results = await embedding_service.embed_services_batch(services)

        assert len(results) == 3
        assert all(svc.id in results for svc in services)
        assert all(len(emb) == 1536 for emb in results.values())

    @pytest.mark.asyncio
    async def test_embed_service_single(
        self, embedding_service: EmbeddingService
    ) -> None:
        """Should embed a single service."""
        service = Mock()
        service.id = "svc_1"
        service.name = "Piano Lessons"
        service.description = "Learn piano"
        service.category = None
        type(service).audience = property(lambda self: None)
        type(service).skill_levels = property(lambda self: None)

        result = await embedding_service.embed_service(service)

        assert result is not None
        assert len(result) == 1536


class TestCacheKeyGeneration:
    """Tests for cache key generation."""

    def test_cache_key_includes_model(
        self, embedding_service: EmbeddingService
    ) -> None:
        """Cache key should include model name."""
        key = embedding_service._query_cache_key("piano lessons")

        assert "embed:" in key
        assert embedding_service.provider.get_model_name() in key

    def test_cache_key_deterministic(
        self, embedding_service: EmbeddingService
    ) -> None:
        """Same query should produce same cache key."""
        key1 = embedding_service._query_cache_key("piano lessons")
        key2 = embedding_service._query_cache_key("piano lessons")

        assert key1 == key2

    def test_cache_key_different_for_different_queries(
        self, embedding_service: EmbeddingService
    ) -> None:
        """Different queries should produce different cache keys."""
        key1 = embedding_service._query_cache_key("piano lessons")
        key2 = embedding_service._query_cache_key("guitar lessons")

        assert key1 != key2
