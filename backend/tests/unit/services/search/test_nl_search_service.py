# backend/tests/unit/services/search/test_nl_search_service.py
"""
Unit tests for NL search service orchestration.

Tests the full search pipeline with mocked components:
- Query parsing
- Candidate retrieval
- Constraint filtering
- Multi-signal ranking
- Response caching
"""
from __future__ import annotations

from datetime import date
from typing import List
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.schemas.nl_search import NLSearchResponse
from app.services.search.filter_service import FilteredCandidate, FilterResult
from app.services.search.nl_search_service import NLSearchService, SearchMetrics
from app.services.search.query_parser import ParsedQuery
from app.services.search.ranking_service import RankedResult, RankingResult
from app.services.search.retriever import RetrievalResult, ServiceCandidate


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
def sample_candidates() -> List[ServiceCandidate]:
    """Create sample service candidates."""
    return [
        ServiceCandidate(
            service_id="svc_001",
            instructor_id="usr_001",
            hybrid_score=0.9,
            vector_score=0.85,
            text_score=0.95,
            name="Piano Lessons",
            description="Learn piano from a pro",
            price_per_hour=50,
        ),
        ServiceCandidate(
            service_id="svc_002",
            instructor_id="usr_002",
            hybrid_score=0.8,
            vector_score=0.75,
            text_score=0.85,
            name="Keyboard Classes",
            description="Piano and keyboard",
            price_per_hour=45,
        ),
    ]


@pytest.fixture
def sample_filtered_candidates() -> List[FilteredCandidate]:
    """Create sample filtered candidates."""
    return [
        FilteredCandidate(
            service_id="svc_001",
            instructor_id="usr_001",
            hybrid_score=0.9,
            name="Piano Lessons",
            description="Learn piano from a pro",
            price_per_hour=50,
            available_dates=[date.today()],
            earliest_available=date.today(),
        ),
        FilteredCandidate(
            service_id="svc_002",
            instructor_id="usr_002",
            hybrid_score=0.8,
            name="Keyboard Classes",
            description="Piano and keyboard",
            price_per_hour=45,
            available_dates=[date.today()],
            earliest_available=date.today(),
        ),
    ]


@pytest.fixture
def sample_ranked_results() -> List[RankedResult]:
    """Create sample ranked results."""
    return [
        RankedResult(
            service_id="svc_001",
            instructor_id="usr_001",
            name="Piano Lessons",
            description="Learn piano from a pro",
            price_per_hour=50,
            final_score=0.87,
            rank=1,
            relevance_score=0.9,
            quality_score=0.85,
            distance_score=0.7,
            price_score=0.9,
            freshness_score=0.95,
            completeness_score=0.8,
            available_dates=[date.today()],
            earliest_available=date.today(),
        ),
        RankedResult(
            service_id="svc_002",
            instructor_id="usr_002",
            name="Keyboard Classes",
            description="Piano and keyboard",
            price_per_hour=45,
            final_score=0.82,
            rank=2,
            relevance_score=0.8,
            quality_score=0.78,
            distance_score=0.65,
            price_score=0.95,
            freshness_score=0.9,
            completeness_score=0.75,
            available_dates=[date.today()],
            earliest_available=date.today(),
        ),
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
        assert service.retriever is not None
        assert service.filter_service is not None
        assert service.ranking_service is not None

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
        result = service._check_cache("piano lessons", None)

        assert result is None

    def test_returns_cached_response_on_hit(self, mock_db: Mock, mock_search_cache: Mock) -> None:
        """Should return cached response on hit."""
        cached = {"results": [], "meta": {"cache_hit": False}}
        mock_search_cache.get_cached_response = Mock(return_value=cached)

        service = NLSearchService(mock_db, search_cache=mock_search_cache)
        result = service._check_cache("piano lessons", None)

        assert result == cached

    def test_handles_cache_error_gracefully(self, mock_db: Mock, mock_search_cache: Mock) -> None:
        """Should handle cache errors gracefully."""
        mock_search_cache.get_cached_response = Mock(side_effect=Exception("Cache error"))

        service = NLSearchService(mock_db, search_cache=mock_search_cache)
        result = service._check_cache("piano lessons", None)

        assert result is None


class TestBuildResponse:
    """Tests for response building."""

    def test_builds_response_with_results(
        self,
        mock_db: Mock,
        sample_parsed_query: ParsedQuery,
        sample_ranked_results: List[RankedResult],
    ) -> None:
        """Should build response with results."""
        service = NLSearchService(mock_db)
        metrics = SearchMetrics(total_latency_ms=150)

        ranking_result = RankingResult(
            results=sample_ranked_results,
            total_results=2,
        )

        response = service._build_response(
            "piano lessons",
            sample_parsed_query,
            ranking_result,
            limit=20,
            metrics=metrics,
        )

        assert isinstance(response, NLSearchResponse)
        assert len(response.results) == 2
        assert response.results[0].rank == 1
        assert response.results[1].rank == 2
        assert response.meta.query == "piano lessons"
        assert response.meta.latency_ms == 150
        assert response.meta.total_results == 2

    def test_respects_limit(
        self,
        mock_db: Mock,
        sample_parsed_query: ParsedQuery,
        sample_ranked_results: List[RankedResult],
    ) -> None:
        """Should respect limit parameter."""
        service = NLSearchService(mock_db)
        metrics = SearchMetrics()

        ranking_result = RankingResult(
            results=sample_ranked_results,
            total_results=2,
        )

        response = service._build_response(
            "piano",
            sample_parsed_query,
            ranking_result,
            limit=1,
            metrics=metrics,
        )

        assert len(response.results) == 1
        assert response.results[0].service_id == "svc_001"

    def test_builds_empty_response(
        self, mock_db: Mock, sample_parsed_query: ParsedQuery
    ) -> None:
        """Should build response with no results."""
        service = NLSearchService(mock_db)
        metrics = SearchMetrics()

        ranking_result = RankingResult(results=[], total_results=0)

        response = service._build_response(
            "nonexistent service",
            sample_parsed_query,
            ranking_result,
            limit=20,
            metrics=metrics,
        )

        assert len(response.results) == 0
        assert response.meta.total_results == 0

    def test_includes_degradation_info(
        self,
        mock_db: Mock,
        sample_parsed_query: ParsedQuery,
        sample_ranked_results: List[RankedResult],
    ) -> None:
        """Should include degradation information in meta."""
        service = NLSearchService(mock_db)
        metrics = SearchMetrics(
            degraded=True,
            degradation_reasons=["embedding_unavailable", "filter_fallback"],
        )

        ranking_result = RankingResult(
            results=sample_ranked_results,
            total_results=2,
        )

        response = service._build_response(
            "piano",
            sample_parsed_query,
            ranking_result,
            limit=20,
            metrics=metrics,
        )

        assert response.meta.degraded is True
        assert "embedding_unavailable" in response.meta.degradation_reasons
        assert "filter_fallback" in response.meta.degradation_reasons

    def test_includes_parsed_query_info(
        self, mock_db: Mock, sample_ranked_results: List[RankedResult]
    ) -> None:
        """Should include parsed query info in meta."""
        service = NLSearchService(mock_db)
        metrics = SearchMetrics()

        parsed = ParsedQuery(
            original_query="cheap piano lessons tomorrow",
            service_query="piano lessons",
            max_price=50,
            date=date.today(),
            parsing_mode="llm",
        )

        ranking_result = RankingResult(
            results=sample_ranked_results,
            total_results=2,
        )

        response = service._build_response(
            "cheap piano lessons tomorrow",
            parsed,
            ranking_result,
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
        sample_candidates: List[ServiceCandidate],
        sample_filtered_candidates: List[FilteredCandidate],
        sample_ranked_results: List[RankedResult],
    ) -> None:
        """Should execute full pipeline on cache miss."""
        # Configure mocks
        mock_search_cache.get_cached_response = Mock(return_value=None)
        mock_search_cache.get_cached_parsed_query = Mock(return_value=None)

        with (
            patch.object(
                NLSearchService, "_parse_query", new_callable=AsyncMock
            ) as mock_parse,
            patch.object(
                NLSearchService, "_retrieve_candidates", new_callable=AsyncMock
            ) as mock_retrieve,
            patch.object(
                NLSearchService, "_filter_candidates", new_callable=AsyncMock
            ) as mock_filter,
            patch.object(
                NLSearchService, "_rank_results"
            ) as mock_rank,
        ):
            mock_parse.return_value = sample_parsed_query
            mock_retrieve.return_value = RetrievalResult(
                candidates=sample_candidates,
                total_candidates=2,
                vector_search_used=True,
                degraded=False,
                degradation_reason=None,
            )
            mock_filter.return_value = FilterResult(
                candidates=sample_filtered_candidates,
                total_before_filter=2,
                total_after_filter=2,
            )
            mock_rank.return_value = RankingResult(
                results=sample_ranked_results,
                total_results=2,
            )

            service = NLSearchService(mock_db, search_cache=mock_search_cache)
            response = await service.search("piano lessons")

            # Verify pipeline was called
            mock_parse.assert_called_once()
            mock_retrieve.assert_called_once()
            mock_filter.assert_called_once()
            mock_rank.assert_called_once()

            # Verify response
            assert isinstance(response, NLSearchResponse)
            assert len(response.results) == 2

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

            # Mock the other pipeline stages
            with (
                patch.object(
                    NLSearchService, "_retrieve_candidates", new_callable=AsyncMock
                ) as mock_retrieve,
                patch.object(
                    NLSearchService, "_filter_candidates", new_callable=AsyncMock
                ) as mock_filter,
                patch.object(
                    NLSearchService, "_rank_results"
                ) as mock_rank,
            ):
                mock_retrieve.return_value = RetrievalResult(
                    candidates=[],
                    total_candidates=0,
                    vector_search_used=False,
                    degraded=True,
                    degradation_reason="parsing_fallback",
                )
                mock_filter.return_value = FilterResult(
                    candidates=[], total_before_filter=0, total_after_filter=0
                )
                mock_rank.return_value = RankingResult(results=[], total_results=0)

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
        sample_candidates: List[ServiceCandidate],
        sample_filtered_candidates: List[FilteredCandidate],
        sample_ranked_results: List[RankedResult],
    ) -> None:
        """Should pass location to filter service."""
        mock_search_cache.get_cached_response = Mock(return_value=None)

        with (
            patch.object(
                NLSearchService, "_parse_query", new_callable=AsyncMock
            ) as mock_parse,
            patch.object(
                NLSearchService, "_retrieve_candidates", new_callable=AsyncMock
            ) as mock_retrieve,
            patch.object(
                NLSearchService, "_filter_candidates", new_callable=AsyncMock
            ) as mock_filter,
            patch.object(
                NLSearchService, "_rank_results"
            ) as mock_rank,
        ):
            mock_parse.return_value = sample_parsed_query
            mock_retrieve.return_value = RetrievalResult(
                candidates=sample_candidates,
                total_candidates=2,
                vector_search_used=True,
                degraded=False,
                degradation_reason=None,
            )
            mock_filter.return_value = FilterResult(
                candidates=sample_filtered_candidates,
                total_before_filter=2,
                total_after_filter=2,
            )
            mock_rank.return_value = RankingResult(
                results=sample_ranked_results,
                total_results=2,
            )

            service = NLSearchService(mock_db, search_cache=mock_search_cache)
            user_location = (-73.95, 40.68)  # Brooklyn

            await service.search("piano", user_location=user_location)

            # Verify location was passed to filter
            call_args = mock_filter.call_args
            assert call_args.kwargs.get("user_location") == user_location or (
                len(call_args.args) > 2 and call_args.args[2] == user_location
            )


class TestResponseCaching:
    """Tests for response caching."""

    def test_caches_response(
        self,
        mock_db: Mock,
        mock_search_cache: Mock,
        sample_parsed_query: ParsedQuery,
        sample_ranked_results: List[RankedResult],
    ) -> None:
        """Should cache response after building."""
        service = NLSearchService(mock_db, search_cache=mock_search_cache)
        metrics = SearchMetrics()

        ranking_result = RankingResult(
            results=sample_ranked_results,
            total_results=2,
        )

        response = service._build_response(
            "piano",
            sample_parsed_query,
            ranking_result,
            limit=20,
            metrics=metrics,
        )

        service._cache_response("piano", None, response)

        mock_search_cache.cache_response.assert_called_once()

    def test_handles_cache_error(
        self,
        mock_db: Mock,
        mock_search_cache: Mock,
        sample_parsed_query: ParsedQuery,
        sample_ranked_results: List[RankedResult],
    ) -> None:
        """Should handle cache error gracefully."""
        mock_search_cache.cache_response = Mock(side_effect=Exception("Cache error"))

        service = NLSearchService(mock_db, search_cache=mock_search_cache)
        metrics = SearchMetrics()

        ranking_result = RankingResult(
            results=sample_ranked_results,
            total_results=2,
        )

        response = service._build_response(
            "piano",
            sample_parsed_query,
            ranking_result,
            limit=20,
            metrics=metrics,
        )

        # Should not raise
        service._cache_response("piano", None, response)
