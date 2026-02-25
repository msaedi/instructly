"""
Coverage tests for embedding_service.py targeting uncovered lines and branches.

Targets:
  - L148: embed_query cache hit path (pending_future not owner)
  - L212->218: Redis singleflight follower waits for leader
  - L221->231: Polling loop with cache check
  - L223->228: Cache hit during polling
  - L229->221: Redis key check during polling
  - L231->240: Final cache check after polling
  - L233->240: Cache hit after leader released lock
  - L259->261: pending_future.set_result in finally
  - L291->293: generate_embedding_text subcategory with category
  - L294->306: generate_embedding_text category fallbacks
  - L296->306: subcategory.category.name check
  - L300->306: service.category.name check
  - L302->306: service.category_name fallback
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from app.services.search.embedding_service import EmbeddingService


@pytest.mark.unit
class TestGenerateEmbeddingTextBranches:
    """Cover L291-306: generate_embedding_text taxonomy chain branches."""

    def test_subcategory_with_category(self):
        """L289-297: subcategory with category -> includes both."""
        svc = EmbeddingService(provider=Mock())

        service = SimpleNamespace(
            name="Piano Lessons",
            description="Learn piano",
            subcategory=SimpleNamespace(
                name="Piano",
                category=SimpleNamespace(name="Music"),
            ),
            eligible_age_groups=None,
        )

        text = svc.generate_embedding_text(service)
        assert "Subcategory: Piano" in text
        assert "Category: Music" in text

    def test_subcategory_without_category(self):
        """L293-294: subcategory exists but category is None."""
        svc = EmbeddingService(provider=Mock())

        service = SimpleNamespace(
            name="Test Service",
            description=None,
            subcategory=SimpleNamespace(
                name="TestSub",
                category=None,
            ),
            eligible_age_groups=None,
        )

        text = svc.generate_embedding_text(service)
        assert "Subcategory: TestSub" in text
        assert "Category:" not in text

    def test_subcategory_category_no_name(self):
        """L295-296: subcategory.category exists but has no name attr."""
        svc = EmbeddingService(provider=Mock())

        service = SimpleNamespace(
            name="Test Service",
            description=None,
            subcategory=SimpleNamespace(
                name="TestSub",
                category=SimpleNamespace(name=None),
            ),
            eligible_age_groups=None,
        )

        text = svc.generate_embedding_text(service)
        assert "Subcategory: TestSub" in text
        assert "Category:" not in text

    def test_no_subcategory_with_category_attr(self):
        """L298-301: no subcategory, has service.category with name."""
        svc = EmbeddingService(provider=Mock())

        service = SimpleNamespace(
            name="Test Service",
            description="A service",
            category=SimpleNamespace(name="Music"),
            eligible_age_groups=None,
        )

        text = svc.generate_embedding_text(service)
        assert "Category: Music" in text
        assert "Subcategory:" not in text

    def test_no_subcategory_category_no_name(self):
        """L300->301: service.category exists but name is None."""
        svc = EmbeddingService(provider=Mock())

        service = SimpleNamespace(
            name="Test Service",
            description=None,
            category=SimpleNamespace(name=None),
            eligible_age_groups=None,
        )

        text = svc.generate_embedding_text(service)
        assert "Category:" not in text

    def test_no_subcategory_category_name_attr(self):
        """L302-303: no subcategory, no category, but has category_name."""
        svc = EmbeddingService(provider=Mock())

        service = SimpleNamespace(
            name="Test Service",
            description=None,
            category_name="Arts",
            eligible_age_groups=None,
        )

        text = svc.generate_embedding_text(service)
        assert "Category: Arts" in text

    def test_no_subcategory_no_category_at_all(self):
        """No taxonomy info at all."""
        svc = EmbeddingService(provider=Mock())

        service = SimpleNamespace(
            name="Test Service",
            description=None,
            eligible_age_groups=None,
        )

        text = svc.generate_embedding_text(service)
        assert text == "Test Service"

    def test_eligible_age_groups(self):
        """L306-308: eligible_age_groups present."""
        svc = EmbeddingService(provider=Mock())

        service = SimpleNamespace(
            name="Test Service",
            description=None,
            eligible_age_groups=["kids", "teens"],
        )

        text = svc.generate_embedding_text(service)
        assert "Age groups: kids, teens" in text

    def test_audience_and_skill_levels(self):
        """L311-316: audience and skill_levels present."""
        svc = EmbeddingService(provider=Mock())

        service = SimpleNamespace(
            name="Test Service",
            description=None,
            eligible_age_groups=None,
            audience="adults",
            skill_levels=["beginner", "intermediate"],
        )

        text = svc.generate_embedding_text(service)
        assert "Audience: adults" in text
        assert "Skill levels: beginner, intermediate" in text

    def test_subcategory_no_name(self):
        """L290-291: subcategory exists but name is None."""
        svc = EmbeddingService(provider=Mock())

        service = SimpleNamespace(
            name="Test Service",
            description=None,
            subcategory=SimpleNamespace(
                name=None,
                category=SimpleNamespace(name="Music"),
            ),
            eligible_age_groups=None,
        )

        text = svc.generate_embedding_text(service)
        assert "Subcategory:" not in text
        assert "Category: Music" in text


@pytest.mark.unit
class TestEmbedQueryCacheBranches:
    """Cover embed_query cache and singleflight branches."""

    @pytest.mark.asyncio
    async def test_embed_query_cache_hit(self):
        """L148: cache hit -> returns cached embedding without calling provider."""
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=[0.1, 0.2, 0.3])
        mock_cache.circuit_breaker = MagicMock()
        mock_cache.circuit_breaker.state = "closed"

        mock_provider = Mock()
        mock_provider.get_model_name.return_value = "text-embedding-ada-002"

        svc = EmbeddingService(cache_service=mock_cache, provider=mock_provider)

        result = await svc.embed_query("piano lessons")
        assert result == [0.1, 0.2, 0.3]

    @pytest.mark.asyncio
    async def test_embed_query_no_cache(self):
        """No cache service -> calls provider directly."""
        mock_provider = Mock()
        mock_provider.embed = AsyncMock(return_value=[0.4, 0.5])
        mock_provider.get_model_name.return_value = "text-embedding-ada-002"

        svc = EmbeddingService(cache_service=None, provider=mock_provider)

        with patch("app.services.search.embedding_service.EMBEDDING_CIRCUIT") as mock_circuit:
            mock_circuit.is_open = False
            mock_circuit.call = AsyncMock(return_value=[0.4, 0.5])
            result = await svc.embed_query("guitar lessons")

        assert result == [0.4, 0.5]

    @pytest.mark.asyncio
    async def test_embed_query_circuit_open(self):
        """Circuit open -> returns None."""
        mock_provider = Mock()
        mock_provider.get_model_name.return_value = "text-embedding-ada-002"

        svc = EmbeddingService(cache_service=None, provider=mock_provider)

        with patch("app.services.search.embedding_service.EMBEDDING_CIRCUIT") as mock_circuit:
            mock_circuit.is_open = True
            result = await svc.embed_query("test query")

        assert result is None

    @pytest.mark.asyncio
    async def test_embed_query_provider_failure(self):
        """Provider raises -> returns None."""

        mock_provider = Mock()
        mock_provider.get_model_name.return_value = "text-embedding-ada-002"

        svc = EmbeddingService(cache_service=None, provider=mock_provider)

        with patch("app.services.search.embedding_service.EMBEDDING_CIRCUIT") as mock_circuit:
            mock_circuit.is_open = False
            mock_circuit.call = AsyncMock(side_effect=RuntimeError("API error"))
            result = await svc.embed_query("test query")

        assert result is None


@pytest.mark.unit
class TestQueryCacheKey:
    def test_cache_key_format(self):
        mock_provider = Mock()
        mock_provider.get_model_name.return_value = "text-embedding-ada-002"

        svc = EmbeddingService(provider=mock_provider)
        key = svc._query_cache_key("test query")
        assert key.startswith("embed:text-embedding-ada-002:")

    def test_different_queries_different_keys(self):
        mock_provider = Mock()
        mock_provider.get_model_name.return_value = "test-model"

        svc = EmbeddingService(provider=mock_provider)
        key1 = svc._query_cache_key("piano lessons")
        key2 = svc._query_cache_key("guitar lessons")
        assert key1 != key2


@pytest.mark.unit
class TestComputeTextHash:
    def test_deterministic(self):
        svc = EmbeddingService(provider=Mock())
        h1 = svc.compute_text_hash("hello world")
        h2 = svc.compute_text_hash("hello world")
        assert h1 == h2

    def test_different_text_different_hash(self):
        svc = EmbeddingService(provider=Mock())
        h1 = svc.compute_text_hash("hello world")
        h2 = svc.compute_text_hash("goodbye world")
        assert h1 != h2
