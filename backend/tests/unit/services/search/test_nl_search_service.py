# backend/tests/unit/services/search/test_nl_search_service.py
"""
Unit tests for NL search service orchestration.

Tests the instructor-level search pipeline with mocked components:
- Query parsing
- Embedding generation
- Instructor retrieval
- Response building
- Response caching
"""
from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.schemas.nl_search import (
    InstructorSummary,
    NLSearchResponse,
    NLSearchResultItem,
    RatingSummary,
    ServiceMatch,
)
from app.services.search.nl_search_service import NLSearchService, SearchMetrics
from app.services.search.query_parser import ParsedQuery


@pytest.fixture
def mock_db() -> Mock:
    """Create mock database session."""
    return Mock()


@pytest.fixture
def mock_cache_service() -> Mock:
    """Create mock cache service."""
    cache = Mock()
    cache.get = Mock(return_value=None)
    cache.set = Mock(return_value=True)
    return cache


@pytest.fixture
def mock_search_cache() -> Mock:
    """Create mock search cache service."""
    cache = Mock()
    cache.get_cached_response = Mock(return_value=None)
    cache.get_cached_parsed_query = Mock(return_value=None)
    cache.cache_response = Mock(return_value=True)
    cache.cache_parsed_query = Mock(return_value=True)
    return cache


@pytest.fixture
def sample_parsed_query() -> ParsedQuery:
    """Create sample parsed query."""
    return ParsedQuery(
        original_query="piano lessons in brooklyn",
        service_query="piano lessons",
        location_text="brooklyn",
        parsing_mode="regex",
    )


@pytest.fixture
def sample_instructor_results() -> List[NLSearchResultItem]:
    """Create sample instructor-level results."""
    return [
        NLSearchResultItem(
            instructor_id="usr_001",
            instructor=InstructorSummary(
                id="usr_001",
                first_name="John",
                last_initial="D",
                profile_picture_url="https://assets.instainstru.com/photo1.jpg",
                bio_snippet="Expert piano teacher with 10 years experience",
                verified=True,
                years_experience=10,
            ),
            rating=RatingSummary(average=4.8, count=25),
            coverage_areas=["Brooklyn", "Manhattan"],
            best_match=ServiceMatch(
                service_id="svc_001",
                service_catalog_id="cat_001",
                name="Piano Lessons",
                description="Learn piano from a pro",
                price_per_hour=50,
                relevance_score=0.9,
            ),
            other_matches=[],
            total_matching_services=1,
            relevance_score=0.9,
        ),
        NLSearchResultItem(
            instructor_id="usr_002",
            instructor=InstructorSummary(
                id="usr_002",
                first_name="Jane",
                last_initial="S",
                profile_picture_url=None,
                bio_snippet="Music theory and keyboard specialist",
                verified=False,
                years_experience=5,
            ),
            rating=RatingSummary(average=4.5, count=12),
            coverage_areas=["Brooklyn"],
            best_match=ServiceMatch(
                service_id="svc_002",
                service_catalog_id="cat_002",
                name="Keyboard Classes",
                description="Piano and keyboard",
                price_per_hour=45,
                relevance_score=0.8,
            ),
            other_matches=[],
            total_matching_services=1,
            relevance_score=0.8,
        ),
    ]


@pytest.fixture
def sample_raw_db_results() -> List[Dict[str, Any]]:
    """Create sample raw DB results from search_with_instructor_data."""
    return [
        {
            "instructor_id": "usr_001",
            "first_name": "John",
            "last_initial": "D",
            "bio_snippet": "Expert piano teacher",
            "years_experience": 10,
            "profile_picture_key": "photos/photo1.jpg",
            "verified": True,
            "matching_services": [
                {
                    "service_id": "svc_001",
                    "service_catalog_id": "cat_001",
                    "name": "Piano Lessons",
                    "description": "Learn piano",
                    "price_per_hour": 50,
                    "relevance_score": 0.9,
                }
            ],
            "best_score": 0.9,
            "match_count": 1,
            "avg_rating": 4.8,
            "review_count": 25,
            "coverage_areas": ["Brooklyn", "Manhattan"],
        },
        {
            "instructor_id": "usr_002",
            "first_name": "Jane",
            "last_initial": "S",
            "bio_snippet": "Music theory specialist",
            "years_experience": 5,
            "profile_picture_key": None,
            "verified": False,
            "matching_services": [
                {
                    "service_id": "svc_002",
                    "service_catalog_id": "cat_002",
                    "name": "Keyboard Classes",
                    "description": "Piano and keyboard",
                    "price_per_hour": 45,
                    "relevance_score": 0.8,
                }
            ],
            "best_score": 0.8,
            "match_count": 1,
            "avg_rating": 4.5,
            "review_count": 12,
            "coverage_areas": ["Brooklyn"],
        },
    ]


class TestSearchMetrics:
    """Tests for SearchMetrics dataclass."""

    def test_default_values(self) -> None:
        """Should initialize with default values."""
        metrics = SearchMetrics()
        assert metrics.total_start == 0
        assert metrics.parse_latency_ms == 0
        assert metrics.cache_hit is False
        assert metrics.degraded is False
        assert metrics.degradation_reasons == []

    def test_degradation_reasons_mutable(self) -> None:
        """Should have independent degradation reasons list."""
        metrics1 = SearchMetrics()
        metrics2 = SearchMetrics()

        metrics1.degradation_reasons.append("test")

        assert metrics1.degradation_reasons == ["test"]
        assert metrics2.degradation_reasons == []


class TestNLSearchServiceInit:
    """Tests for NLSearchService initialization."""

    def test_initializes_with_db(self, mock_db: Mock) -> None:
        """Should initialize with just db session."""
        service = NLSearchService(mock_db)

        assert service.db is mock_db
        assert service.search_cache is not None
        assert service.embedding_service is not None
        assert service.parser is not None
        assert service.retriever_repository is not None

    def test_accepts_custom_search_cache(self, mock_db: Mock, mock_search_cache: Mock) -> None:
        """Should accept custom search cache."""
        service = NLSearchService(mock_db, search_cache=mock_search_cache)

        assert service.search_cache is mock_search_cache


class TestCacheCheck:
    """Tests for cache check logic."""

    def test_returns_none_on_cache_miss(self, mock_db: Mock, mock_search_cache: Mock) -> None:
        """Should return None on cache miss."""
        mock_search_cache.get_cached_response = Mock(return_value=None)

        service = NLSearchService(mock_db, search_cache=mock_search_cache)
        result = service._check_cache("piano lessons", None, limit=20)

        assert result is None

    def test_returns_cached_response_on_hit(self, mock_db: Mock, mock_search_cache: Mock) -> None:
        """Should return cached response on hit."""
        cached = {"results": [], "meta": {"cache_hit": False}}
        mock_search_cache.get_cached_response = Mock(return_value=cached)

        service = NLSearchService(mock_db, search_cache=mock_search_cache)
        result = service._check_cache("piano lessons", None, limit=20)

        assert result == cached

    def test_handles_cache_error_gracefully(self, mock_db: Mock, mock_search_cache: Mock) -> None:
        """Should handle cache errors gracefully."""
        mock_search_cache.get_cached_response = Mock(side_effect=Exception("Cache error"))

        service = NLSearchService(mock_db, search_cache=mock_search_cache)
        result = service._check_cache("piano lessons", None, limit=20)

        assert result is None


class TestBuildInstructorResponse:
    """Tests for instructor-level response building."""

    def test_builds_response_with_results(
        self,
        mock_db: Mock,
        sample_parsed_query: ParsedQuery,
        sample_instructor_results: List[NLSearchResultItem],
    ) -> None:
        """Should build response with instructor-level results."""
        service = NLSearchService(mock_db)
        metrics = SearchMetrics(total_latency_ms=150)

        response = service._build_instructor_response(
            "piano lessons",
            sample_parsed_query,
            sample_instructor_results,
            limit=20,
            metrics=metrics,
        )

        assert isinstance(response, NLSearchResponse)
        assert len(response.results) == 2
        assert response.results[0].instructor_id == "usr_001"
        assert response.results[1].instructor_id == "usr_002"
        assert response.meta.query == "piano lessons"
        assert response.meta.latency_ms == 150
        assert response.meta.total_results == 2

    def test_respects_limit(
        self,
        mock_db: Mock,
        sample_parsed_query: ParsedQuery,
        sample_instructor_results: List[NLSearchResultItem],
    ) -> None:
        """Should respect limit parameter."""
        service = NLSearchService(mock_db)
        metrics = SearchMetrics()

        response = service._build_instructor_response(
            "piano",
            sample_parsed_query,
            sample_instructor_results,
            limit=1,
            metrics=metrics,
        )

        assert len(response.results) == 1
        assert response.results[0].instructor_id == "usr_001"

    def test_builds_empty_response(
        self, mock_db: Mock, sample_parsed_query: ParsedQuery
    ) -> None:
        """Should build response with no results."""
        service = NLSearchService(mock_db)
        metrics = SearchMetrics()

        response = service._build_instructor_response(
            "nonexistent service",
            sample_parsed_query,
            [],
            limit=20,
            metrics=metrics,
        )

        assert len(response.results) == 0
        assert response.meta.total_results == 0

    def test_includes_degradation_info(
        self,
        mock_db: Mock,
        sample_parsed_query: ParsedQuery,
        sample_instructor_results: List[NLSearchResultItem],
    ) -> None:
        """Should include degradation information in meta."""
        service = NLSearchService(mock_db)
        metrics = SearchMetrics(
            degraded=True,
            degradation_reasons=["embedding_unavailable", "filter_fallback"],
        )

        response = service._build_instructor_response(
            "piano",
            sample_parsed_query,
            sample_instructor_results,
            limit=20,
            metrics=metrics,
        )

        assert response.meta.degraded is True
        assert "embedding_unavailable" in response.meta.degradation_reasons
        assert "filter_fallback" in response.meta.degradation_reasons

    def test_includes_parsed_query_info(
        self, mock_db: Mock, sample_instructor_results: List[NLSearchResultItem]
    ) -> None:
        """Should include parsed query info in meta."""
        from datetime import date

        service = NLSearchService(mock_db)
        metrics = SearchMetrics()

        parsed = ParsedQuery(
            original_query="cheap piano lessons tomorrow",
            service_query="piano lessons",
            max_price=50,
            date=date.today(),
            parsing_mode="llm",
        )

        response = service._build_instructor_response(
            "cheap piano lessons tomorrow",
            parsed,
            sample_instructor_results,
            limit=20,
            metrics=metrics,
        )

        assert response.meta.parsed.service_query == "piano lessons"
        assert response.meta.parsed.max_price == 50
        assert response.meta.parsed.date is not None
        assert response.meta.parsing_mode == "llm"


class TestSearchPipeline:
    """Tests for full search pipeline."""

    @pytest.mark.asyncio
    async def test_returns_cached_response(
        self, mock_db: Mock, mock_search_cache: Mock
    ) -> None:
        """Should return cached response on cache hit."""
        cached_response = {
            "results": [],
            "meta": {
                "query": "piano",
                "parsed": {"service_query": "piano"},
                "total_results": 0,
                "limit": 20,
                "latency_ms": 50,
                "cache_hit": False,
                "degraded": False,
                "degradation_reasons": [],
                "parsing_mode": "regex",
            },
        }
        mock_search_cache.get_cached_response = Mock(return_value=cached_response)

        service = NLSearchService(mock_db, search_cache=mock_search_cache)
        response = await service.search("piano")

        assert isinstance(response, NLSearchResponse)
        assert response.meta.cache_hit is True

    @pytest.mark.asyncio
    async def test_full_pipeline_on_cache_miss(
        self,
        mock_db: Mock,
        mock_search_cache: Mock,
        sample_parsed_query: ParsedQuery,
        sample_raw_db_results: List[Dict[str, Any]],
    ) -> None:
        """Should execute full instructor-level pipeline on cache miss."""
        # Configure mocks
        mock_search_cache.get_cached_response = Mock(return_value=None)
        mock_search_cache.get_cached_parsed_query = Mock(return_value=None)

        with (
            patch.object(
                NLSearchService, "_parse_query", new_callable=AsyncMock
            ) as mock_parse,
            patch(
                "app.services.search.nl_search_service.EmbeddingService"
            ) as mock_embedding_class,
            patch(
                "app.services.search.nl_search_service.RetrieverRepository"
            ) as mock_repo_class,
        ):
            mock_parse.return_value = sample_parsed_query

            # Mock embedding service
            mock_embedding_instance = Mock()
            mock_embedding_instance.embed_query = AsyncMock(return_value=[0.1] * 1536)
            mock_embedding_class.return_value = mock_embedding_instance

            # Mock retriever repository
            mock_repo_instance = Mock()
            mock_repo_instance.search_with_instructor_data = Mock(
                return_value=sample_raw_db_results
            )
            mock_repo_class.return_value = mock_repo_instance

            service = NLSearchService(mock_db, search_cache=mock_search_cache)
            # Inject mocked components
            service.embedding_service = mock_embedding_instance
            service.retriever_repository = mock_repo_instance

            response = await service.search("piano lessons")

            # Verify pipeline was called
            mock_parse.assert_called_once()
            mock_embedding_instance.embed_query.assert_called_once()

            # Verify response
            assert isinstance(response, NLSearchResponse)
            assert len(response.results) == 2
            assert response.results[0].instructor_id == "usr_001"

    @pytest.mark.asyncio
    async def test_handles_parsing_failure(
        self, mock_db: Mock, mock_search_cache: Mock, sample_parsed_query: ParsedQuery
    ) -> None:
        """Should handle parsing failure gracefully."""
        mock_search_cache.get_cached_response = Mock(return_value=None)
        mock_search_cache.get_cached_parsed_query = Mock(return_value=None)

        with (
            patch(
                "app.services.search.nl_search_service.hybrid_parse",
                new_callable=AsyncMock,
            ) as mock_hybrid_parse,
            patch(
                "app.services.search.nl_search_service.QueryParser"
            ) as mock_parser_class,
        ):
            mock_hybrid_parse.side_effect = Exception("Parse error")
            # Mock the fallback parser
            mock_parser = Mock()
            mock_parser.parse.return_value = sample_parsed_query
            mock_parser_class.return_value = mock_parser

            service = NLSearchService(mock_db, search_cache=mock_search_cache)

            # Mock embedding to return None (no vector search)
            with patch.object(
                service.embedding_service, "embed_query", new_callable=AsyncMock
            ) as mock_embed:
                mock_embed.return_value = None

                response = await service.search("piano")

                assert isinstance(response, NLSearchResponse)
                assert response.meta.degraded is True
                assert "parsing_error" in response.meta.degradation_reasons


class TestLocationHandling:
    """Tests for location parameter handling."""

    @pytest.mark.asyncio
    async def test_passes_location_to_filter(
        self,
        mock_db: Mock,
        mock_search_cache: Mock,
        sample_parsed_query: ParsedQuery,
        sample_raw_db_results: List[Dict[str, Any]],
    ) -> None:
        """Should pass location through the pipeline."""
        mock_search_cache.get_cached_response = Mock(return_value=None)
        mock_search_cache.get_cached_parsed_query = Mock(return_value=None)

        with (
            patch.object(
                NLSearchService, "_parse_query", new_callable=AsyncMock
            ) as mock_parse,
        ):
            mock_parse.return_value = sample_parsed_query

            service = NLSearchService(mock_db, search_cache=mock_search_cache)

            # Mock embedding service
            with patch.object(
                service.embedding_service, "embed_query", new_callable=AsyncMock
            ) as mock_embed:
                mock_embed.return_value = [0.1] * 1536

                # Mock retriever repository
                with patch.object(
                    service.retriever_repository, "search_with_instructor_data"
                ) as mock_search:
                    mock_search.return_value = sample_raw_db_results

                    user_location = (-73.95, 40.68)  # Brooklyn
                    await service.search("piano", user_location=user_location)

                    # Verify embedding was called
                    mock_embed.assert_called_once()


class TestResponseCaching:
    """Tests for response caching."""

    def test_caches_response(
        self,
        mock_db: Mock,
        mock_search_cache: Mock,
        sample_parsed_query: ParsedQuery,
        sample_instructor_results: List[NLSearchResultItem],
    ) -> None:
        """Should cache response after building."""
        service = NLSearchService(mock_db, search_cache=mock_search_cache)
        metrics = SearchMetrics()

        response = service._build_instructor_response(
            "piano",
            sample_parsed_query,
            sample_instructor_results,
            limit=20,
            metrics=metrics,
        )

        service._cache_response("piano", None, response, limit=20)

        mock_search_cache.cache_response.assert_called_once()

    def test_handles_cache_error(
        self,
        mock_db: Mock,
        mock_search_cache: Mock,
        sample_parsed_query: ParsedQuery,
        sample_instructor_results: List[NLSearchResultItem],
    ) -> None:
        """Should handle cache error gracefully."""
        mock_search_cache.cache_response = Mock(side_effect=Exception("Cache error"))

        service = NLSearchService(mock_db, search_cache=mock_search_cache)
        metrics = SearchMetrics()

        response = service._build_instructor_response(
            "piano",
            sample_parsed_query,
            sample_instructor_results,
            limit=20,
            metrics=metrics,
        )

        # Should not raise
        service._cache_response("piano", None, response, limit=20)
