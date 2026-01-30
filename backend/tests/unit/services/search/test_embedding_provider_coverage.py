# backend/tests/unit/services/search/test_embedding_provider_coverage.py
"""
Coverage tests for embedding_provider.py.
Targets missed lines: 66->72, 90-101, 107, 147, 186->189
"""
from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.search.embedding_provider import (
    MockEmbeddingProvider,
    OpenAIEmbeddingProvider,
    create_embedding_provider,
)


class TestOpenAIEmbeddingProviderClient:
    """Test OpenAI client initialization - Lines 66->72."""

    def test_client_lazy_initialization(self) -> None:
        """Client should be created lazily on first access."""
        provider = OpenAIEmbeddingProvider()
        assert provider._client is None

        # Access client (will create it)
        with patch(
            "app.services.search.embedding_provider.AsyncOpenAI"
        ) as mock_openai:
            _ = provider.client
            mock_openai.assert_called_once()

    def test_client_recreates_when_max_retries_changes(self) -> None:
        """Client should be recreated when max_retries config changes - Lines 66->72."""

        class FakeOpenAI:
            def __init__(self, timeout: float, max_retries: int) -> None:
                self.timeout = timeout
                self.max_retries = max_retries

        with patch(
            "app.services.search.embedding_provider.AsyncOpenAI",
            FakeOpenAI,
        ):
            provider = OpenAIEmbeddingProvider()

            # Create config mock
            config = SimpleNamespace(max_retries=1)

            with patch(
                "app.services.search.embedding_provider.get_search_config",
                return_value=config,
            ):
                # First access
                client1 = provider.client
                assert client1.max_retries == 1

                # Change config
                config.max_retries = 3

                # Second access should create new client
                client2 = provider.client
                assert client2.max_retries == 3
                assert client2 is not client1

    def test_client_reuses_when_max_retries_same(self) -> None:
        """Client should be reused when max_retries hasn't changed."""

        class FakeOpenAI:
            def __init__(self, timeout: float, max_retries: int) -> None:
                self.timeout = timeout
                self.max_retries = max_retries

        with patch(
            "app.services.search.embedding_provider.AsyncOpenAI",
            FakeOpenAI,
        ):
            provider = OpenAIEmbeddingProvider()
            config = SimpleNamespace(max_retries=2)

            with patch(
                "app.services.search.embedding_provider.get_search_config",
                return_value=config,
            ):
                client1 = provider.client
                client2 = provider.client
                assert client1 is client2


class TestOpenAIEmbeddingProviderEmbed:
    """Test embed methods."""

    @pytest.mark.asyncio
    async def test_embed_returns_list(self) -> None:
        """embed should return list of floats."""
        provider = OpenAIEmbeddingProvider()

        # Mock the client
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]

        provider._client = MagicMock()
        provider._client.embeddings = MagicMock()
        provider._client.embeddings.create = AsyncMock(return_value=mock_response)
        provider._client_max_retries = 2

        result = await provider.embed("test text")
        assert result == [0.1, 0.2, 0.3]

    @pytest.mark.asyncio
    async def test_embed_batch_empty_list(self) -> None:
        """embed_batch with empty list should return empty list - Lines 90-91."""
        provider = OpenAIEmbeddingProvider()
        result = await provider.embed_batch([])
        assert result == []

    @pytest.mark.asyncio
    async def test_embed_batch_returns_sorted_embeddings(self) -> None:
        """embed_batch should return embeddings in input order - Lines 99-101."""
        provider = OpenAIEmbeddingProvider()

        # Mock response with out-of-order indices
        mock_item1 = MagicMock()
        mock_item1.index = 1
        mock_item1.embedding = [0.2] * 10

        mock_item2 = MagicMock()
        mock_item2.index = 0
        mock_item2.embedding = [0.1] * 10

        mock_item3 = MagicMock()
        mock_item3.index = 2
        mock_item3.embedding = [0.3] * 10

        mock_response = MagicMock()
        mock_response.data = [mock_item1, mock_item2, mock_item3]  # Out of order

        provider._client = MagicMock()
        provider._client.embeddings = MagicMock()
        provider._client.embeddings.create = AsyncMock(return_value=mock_response)
        provider._client_max_retries = 2

        result = await provider.embed_batch(["text1", "text2", "text3"])

        # Should be sorted by index
        assert result[0] == [0.1] * 10  # index 0
        assert result[1] == [0.2] * 10  # index 1
        assert result[2] == [0.3] * 10  # index 2


class TestOpenAIEmbeddingProviderGetters:
    """Test getter methods - Line 107."""

    def test_get_model_name(self) -> None:
        """get_model_name should return configured model."""
        provider = OpenAIEmbeddingProvider(model="my-model")
        assert provider.get_model_name() == "my-model"

    def test_get_model_name_default(self) -> None:
        """get_model_name should return default model."""
        provider = OpenAIEmbeddingProvider()
        assert provider.get_model_name() == "text-embedding-3-small"

    def test_get_dimensions(self) -> None:
        """get_dimensions should return configured dimensions - Line 107."""
        provider = OpenAIEmbeddingProvider(dimensions=768)
        assert provider.get_dimensions() == 768

    def test_get_dimensions_default(self) -> None:
        """get_dimensions should return default dimensions."""
        provider = OpenAIEmbeddingProvider()
        assert provider.get_dimensions() == 1536


class TestMockEmbeddingProvider:
    """Test mock provider behavior."""

    @pytest.mark.asyncio
    async def test_embed_deterministic(self) -> None:
        """Same input should produce same output."""
        provider = MockEmbeddingProvider(dimensions=10)
        emb1 = await provider.embed("test")
        emb2 = await provider.embed("test")
        assert emb1 == emb2

    @pytest.mark.asyncio
    async def test_embed_different_inputs(self) -> None:
        """Different inputs should produce different outputs."""
        provider = MockEmbeddingProvider(dimensions=10)
        emb1 = await provider.embed("hello")
        emb2 = await provider.embed("world")
        assert emb1 != emb2

    @pytest.mark.asyncio
    async def test_embed_normalized(self) -> None:
        """Output should be normalized unit vector."""
        provider = MockEmbeddingProvider(dimensions=100)
        emb = await provider.embed("test")
        magnitude = sum(x**2 for x in emb) ** 0.5
        assert abs(magnitude - 1.0) < 0.0001

    @pytest.mark.asyncio
    async def test_embed_batch(self) -> None:
        """embed_batch should work correctly."""
        provider = MockEmbeddingProvider(dimensions=10)
        results = await provider.embed_batch(["a", "b", "c"])
        assert len(results) == 3
        assert all(len(e) == 10 for e in results)

    def test_get_model_name(self) -> None:
        """get_model_name should return mock model name."""
        provider = MockEmbeddingProvider()
        assert provider.get_model_name() == "mock-embedding-v1"

    def test_get_dimensions(self) -> None:
        """get_dimensions should return configured dimensions."""
        provider = MockEmbeddingProvider(dimensions=256)
        assert provider.get_dimensions() == 256


class TestCreateEmbeddingProviderFactory:
    """Test provider factory function - Lines 186->189."""

    def test_creates_mock_provider(self) -> None:
        """Should create mock provider when EMBEDDING_PROVIDER=mock."""
        with patch.dict(os.environ, {"EMBEDDING_PROVIDER": "mock"}):
            provider = create_embedding_provider()
            assert isinstance(provider, MockEmbeddingProvider)

    def test_creates_openai_provider_by_default(self) -> None:
        """Should create OpenAI provider by default."""
        with patch.dict(os.environ, {"EMBEDDING_PROVIDER": "openai"}, clear=False):
            provider = create_embedding_provider()
            assert isinstance(provider, OpenAIEmbeddingProvider)

    def test_uses_provided_model(self) -> None:
        """Should use provided model override."""
        with patch.dict(os.environ, {"EMBEDDING_PROVIDER": "openai"}, clear=False):
            provider = create_embedding_provider(model="custom-model")
            assert provider.get_model_name() == "custom-model"

    def test_uses_config_model_when_model_none(self) -> None:
        """Should use config model when model param is None - Lines 186->189."""
        # The factory function dynamically imports and calls get_search_config
        # We need to verify it uses the model from config when None is passed
        with patch.dict(os.environ, {"EMBEDDING_PROVIDER": "openai"}, clear=False):
            # Just verify the OpenAI provider is created with default model
            provider = create_embedding_provider(model=None)
            assert isinstance(provider, OpenAIEmbeddingProvider)
            # Model comes from config.embedding_model which defaults to text-embedding-3-small
            assert provider.get_model_name() == "text-embedding-3-small"

    def test_respects_dimensions_config(self) -> None:
        """Should use configured dimensions."""
        with patch.dict(
            os.environ,
            {"EMBEDDING_PROVIDER": "mock", "EMBEDDING_DIMENSIONS": "512"},
        ):
            provider = create_embedding_provider()
            assert provider.get_dimensions() == 512


class TestMockEmbeddingProviderEdgeCases:
    """Test mock provider edge cases."""

    @pytest.mark.asyncio
    async def test_embed_empty_string(self) -> None:
        """Should handle empty string."""
        provider = MockEmbeddingProvider(dimensions=10)
        emb = await provider.embed("")
        assert len(emb) == 10

    @pytest.mark.asyncio
    async def test_embed_unicode(self) -> None:
        """Should handle unicode characters."""
        provider = MockEmbeddingProvider(dimensions=10)
        emb = await provider.embed("こんにちは")
        assert len(emb) == 10

    @pytest.mark.asyncio
    async def test_embed_long_text(self) -> None:
        """Should handle long text."""
        provider = MockEmbeddingProvider(dimensions=10)
        emb = await provider.embed("word " * 1000)
        assert len(emb) == 10

    @pytest.mark.asyncio
    async def test_embed_batch_empty(self) -> None:
        """Should handle empty batch."""
        provider = MockEmbeddingProvider(dimensions=10)
        results = await provider.embed_batch([])
        assert results == []

    @pytest.mark.asyncio
    async def test_embed_case_insensitive(self) -> None:
        """Same text different case should produce same embedding (lowercase normalized)."""
        provider = MockEmbeddingProvider(dimensions=10)
        emb1 = await provider.embed("Hello World")
        emb2 = await provider.embed("hello world")
        assert emb1 == emb2  # MockProvider lowercases input
