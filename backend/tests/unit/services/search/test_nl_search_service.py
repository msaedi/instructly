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
from app.services.search.filter_service import FilterResult
from app.services.search.location_resolver import ResolvedLocation
from app.services.search.nl_search_service import (
    NLSearchService,
    PostOpenAIData,
    PreOpenAIData,
    SearchMetrics,
)
from app.services.search.query_parser import ParsedQuery
from app.services.search.ranking_service import RankedResult, RankingResult


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
    cache = AsyncMock()
    cache.get_cached_response = AsyncMock(return_value=None)
    cache.get_cached_parsed_query = AsyncMock(return_value=None)
    cache.cache_response = AsyncMock(return_value=True)
    cache.cache_parsed_query = AsyncMock(return_value=True)
    return cache  # type: ignore[return-value]


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

    def test_initializes(self) -> None:
        """Should initialize with default dependencies."""
        service = NLSearchService()

        assert service.search_cache is not None
        assert service.embedding_service is not None
        assert service.retriever is not None
        assert service.filter_service is not None
        assert service.ranking_service is not None

    def test_accepts_custom_search_cache(self, mock_search_cache: Mock) -> None:
        """Should accept custom search cache."""
        service = NLSearchService(search_cache=mock_search_cache)

        assert service.search_cache is mock_search_cache


class TestCacheCheck:
    """Tests for cache check logic."""

    @pytest.mark.asyncio
    async def test_returns_none_on_cache_miss(self, mock_search_cache: Mock) -> None:
        """Should return None on cache miss."""
        mock_search_cache.get_cached_response.return_value = None

        service = NLSearchService(search_cache=mock_search_cache)
        result = await service._check_cache("piano lessons", None, limit=20)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_cached_response_on_hit(self, mock_search_cache: Mock) -> None:
        """Should return cached response on hit."""
        cached = {"results": [], "meta": {"cache_hit": False}}
        mock_search_cache.get_cached_response.return_value = cached

        service = NLSearchService(search_cache=mock_search_cache)
        result = await service._check_cache("piano lessons", None, limit=20)

        assert result == cached

    @pytest.mark.asyncio
    async def test_handles_cache_error_gracefully(self, mock_search_cache: Mock) -> None:
        """Should handle cache errors gracefully."""
        mock_search_cache.get_cached_response.side_effect = Exception("Cache error")

        service = NLSearchService(search_cache=mock_search_cache)
        result = await service._check_cache("piano lessons", None, limit=20)

        assert result is None


class TestBuildInstructorResponse:
    """Tests for instructor-level response building."""

    def test_builds_response_with_results(
        self,
        sample_parsed_query: ParsedQuery,
        sample_instructor_results: List[NLSearchResultItem],
    ) -> None:
        """Should build response with instructor-level results."""
        service = NLSearchService()
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
        sample_parsed_query: ParsedQuery,
        sample_instructor_results: List[NLSearchResultItem],
    ) -> None:
        """Should respect limit parameter."""
        service = NLSearchService()
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

    def test_builds_empty_response(self, sample_parsed_query: ParsedQuery) -> None:
        """Should build response with no results."""
        service = NLSearchService()
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
        sample_parsed_query: ParsedQuery,
        sample_instructor_results: List[NLSearchResultItem],
    ) -> None:
        """Should include degradation information in meta."""
        service = NLSearchService()
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
        self, sample_instructor_results: List[NLSearchResultItem]
    ) -> None:
        """Should include parsed query info in meta."""
        from datetime import date

        service = NLSearchService()
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


class TestTransformInstructorResults:
    """Tests for transforming raw instructor results into response schema."""

    def test_recomputes_best_match_after_price_filter(self) -> None:
        """
        Price filtering must update best_match + relevance_score.

        Regression test for ranking correctness: if an instructor's top-scoring
        service is filtered out by max_price, the instructor must be ranked by
        the best remaining affordable service (not the filtered one).
        """
        service = NLSearchService()
        parsed = ParsedQuery(
            original_query="jazz improv under $60",
            service_query="jazz improv",
            max_price=60,
            parsing_mode="regex",
        )

        raw_results: List[Dict[str, Any]] = [
            {
                "instructor_id": "usr_A",
                "first_name": "Alice",
                "last_initial": "A",
                "bio_snippet": "Jazz teacher",
                "years_experience": 10,
                "profile_picture_key": None,
                "verified": True,
                "matching_services": [
                    {
                        "service_id": "svc_expensive",
                        "service_catalog_id": "cat_expensive",
                        "name": "Jazz Improv",
                        "description": "Advanced improv",
                        "price_per_hour": 150,
                        "relevance_score": 0.95,
                    },
                    {
                        "service_id": "svc_affordable",
                        "service_catalog_id": "cat_affordable",
                        "name": "Basic Guitar",
                        "description": "Guitar basics",
                        "price_per_hour": 50,
                        "relevance_score": 0.40,
                    },
                ],
                "best_score": 0.95,
                "match_count": 2,
                "avg_rating": 4.9,
                "review_count": 25,
                "coverage_areas": ["Manhattan"],
            },
            {
                "instructor_id": "usr_B",
                "first_name": "Bob",
                "last_initial": "B",
                "bio_snippet": "Affordable jazz teacher",
                "years_experience": 5,
                "profile_picture_key": None,
                "verified": False,
                "matching_services": [
                    {
                        "service_id": "svc_b1",
                        "service_catalog_id": "cat_b1",
                        "name": "Jazz Basics",
                        "description": "Intro improv",
                        "price_per_hour": 55,
                        "relevance_score": 0.50,
                    },
                ],
                "best_score": 0.50,
                "match_count": 1,
                "avg_rating": 4.7,
                "review_count": 10,
                "coverage_areas": ["Brooklyn"],
            },
        ]

        results = service._transform_instructor_results(raw_results, parsed)
        results.sort(key=lambda r: r.relevance_score, reverse=True)

        assert [r.instructor_id for r in results] == ["usr_B", "usr_A"]

        assert results[0].best_match.service_id == "svc_b1"
        assert results[0].relevance_score == 0.5

        assert results[1].best_match.service_id == "svc_affordable"
        assert results[1].relevance_score == 0.4
        assert results[1].total_matching_services == 1
        assert results[1].other_matches == []


class TestHydrateInstructorResults:
    """Tests for converting ranked candidates into instructor-level results."""

    @pytest.mark.asyncio
    async def test_groups_by_instructor_and_picks_best_match_by_relevance(self) -> None:
        service = NLSearchService()

        ranked = [
            RankedResult(
                service_id="svc_a1",
                service_catalog_id="cat_a1",
                instructor_id="usr_A",
                name="Guitar",
                description=None,
                price_per_hour=100,
                final_score=0.9,
                rank=1,
                relevance_score=0.4,
                quality_score=0.8,
                distance_score=0.5,
                price_score=0.3,
                freshness_score=0.6,
                completeness_score=0.7,
            ),
            RankedResult(
                service_id="svc_b1",
                service_catalog_id="cat_b1",
                instructor_id="usr_B",
                name="Piano",
                description=None,
                price_per_hour=80,
                final_score=0.85,
                rank=2,
                relevance_score=0.7,
                quality_score=0.7,
                distance_score=0.5,
                price_score=0.4,
                freshness_score=0.6,
                completeness_score=0.7,
            ),
            RankedResult(
                service_id="svc_a2",
                service_catalog_id="cat_a2",
                instructor_id="usr_A",
                name="Jazz Guitar",
                description=None,
                price_per_hour=120,
                final_score=0.8,
                rank=3,
                relevance_score=0.95,
                quality_score=0.8,
                distance_score=0.5,
                price_score=0.3,
                freshness_score=0.6,
                completeness_score=0.7,
            ),
        ]

        instructor_cards = [
            {
                "instructor_id": "usr_A",
                "first_name": "Alice",
                "last_initial": "A",
                "bio_snippet": "A bio",
                "years_experience": 10,
                "profile_picture_key": "photos/usr_A.jpg",
                "verified": True,
                "avg_rating": 4.9,
                "review_count": 50,
                "coverage_areas": ["Brooklyn"],
            },
            {
                "instructor_id": "usr_B",
                "first_name": "Bob",
                "last_initial": "B",
                "bio_snippet": "B bio",
                "years_experience": 5,
                "profile_picture_key": None,
                "verified": False,
                "avg_rating": 4.7,
                "review_count": 10,
                "coverage_areas": ["Manhattan"],
            },
        ]

        class _DummySessionCtx:
            def __enter__(self) -> Mock:  # type: ignore[override]
                return Mock()

            def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
                return None

        with (
            patch("app.services.search.nl_search_service.get_db_session", return_value=_DummySessionCtx()),
            patch("app.repositories.retriever_repository.RetrieverRepository") as mock_repo_cls,
        ):
            mock_repo_cls.return_value.get_instructor_cards = Mock(return_value=instructor_cards)
            results = await service._hydrate_instructor_results(ranked, limit=2)

        assert [r.instructor_id for r in results] == ["usr_A", "usr_B"]
        assert results[0].best_match.service_id == "svc_a2"
        assert [m.service_id for m in results[0].other_matches] == ["svc_a1"]
        assert results[0].total_matching_services == 2
        assert results[0].rating.count == 50
        assert results[0].coverage_areas == ["Brooklyn"]
        assert results[0].instructor.profile_picture_url
        assert results[0].instructor.profile_picture_url.endswith("photos/usr_A.jpg")


class TestSearchPipeline:
    """Tests for full search pipeline."""

    @pytest.mark.asyncio
    async def test_returns_cached_response(self, mock_search_cache: Mock) -> None:
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
        mock_search_cache.get_cached_response.return_value = cached_response

        service = NLSearchService(search_cache=mock_search_cache)
        response = await service.search("piano")

        assert isinstance(response, NLSearchResponse)
        assert response.meta.cache_hit is True

    @pytest.mark.asyncio
    async def test_full_pipeline_on_cache_miss(
        self,
        mock_search_cache: Mock,
        sample_parsed_query: ParsedQuery,
        sample_instructor_results: List[NLSearchResultItem],
    ) -> None:
        """Should execute full pipeline and cache non-degraded responses."""
        mock_search_cache.get_cached_response.return_value = None
        mock_search_cache.get_cached_parsed_query.return_value = None

        service = NLSearchService(search_cache=mock_search_cache)

        pre_data = PreOpenAIData(
            parsed_query=sample_parsed_query,
            parse_latency_ms=5,
            text_results={},
            text_latency_ms=0,
            has_service_embeddings=True,
            best_text_score=0.0,
            require_text_match=False,
            skip_vector=False,
            region_lookup=None,
            location_resolution=ResolvedLocation.from_not_found(),
            location_normalized=None,
            cached_alias_normalized=None,
            fuzzy_score=None,
        )
        post_data = PostOpenAIData(
            filter_result=FilterResult(
                candidates=[],
                total_before_filter=1,
                total_after_filter=0,
                filters_applied=[],
                soft_filtering_used=False,
            ),
            ranking_result=RankingResult(results=[], total_results=0),
            retrieval_candidates=[],
            instructor_rows=[],
            distance_meters={},
            text_latency_ms=0,
            vector_latency_ms=0,
            filter_latency_ms=0,
            rank_latency_ms=0,
            vector_search_used=True,
            total_candidates=1,
            filter_failed=False,
            ranking_failed=False,
            skip_vector=False,
        )

        with (
            patch.object(service, "_run_pre_openai_burst", return_value=pre_data) as mock_pre,
            patch.object(
                service,
                "_embed_query_with_timeout",
                new_callable=AsyncMock,
                return_value=([0.1], 5, None),
            ) as mock_embed,
            patch.object(service, "_run_post_openai_burst", return_value=post_data) as mock_post,
            patch.object(
                service, "_hydrate_instructor_results", new_callable=AsyncMock
            ) as mock_hydrate,
            patch("app.services.search.nl_search_service.record_search_metrics") as mock_metrics,
        ):
            mock_hydrate.return_value = sample_instructor_results

            response = await service.search("piano lessons", user_location=(-73.95, 40.68))

            assert isinstance(response, NLSearchResponse)
            assert len(response.results) == 2
            assert response.meta.degraded is False
            mock_pre.assert_called_once()
            mock_embed.assert_awaited_once()
            mock_post.assert_called_once()
            mock_hydrate.assert_awaited_once()
            mock_search_cache.cache_response.assert_awaited_once()
            mock_metrics.assert_called_once()

    @pytest.mark.asyncio
    async def test_falls_back_to_text_only_when_embedding_unavailable(
        self,
        mock_search_cache: Mock,
        sample_parsed_query: ParsedQuery,
        sample_instructor_results: List[NLSearchResultItem],
    ) -> None:
        """Should mark degraded and cache response briefly when embeddings unavailable."""
        mock_search_cache.get_cached_response.return_value = None
        mock_search_cache.get_cached_parsed_query.return_value = None

        service = NLSearchService(search_cache=mock_search_cache)
        pre_data = PreOpenAIData(
            parsed_query=sample_parsed_query,
            parse_latency_ms=5,
            text_results={},
            text_latency_ms=0,
            has_service_embeddings=True,
            best_text_score=0.0,
            require_text_match=False,
            skip_vector=False,
            region_lookup=None,
            location_resolution=ResolvedLocation.from_not_found(),
            location_normalized=None,
            cached_alias_normalized=None,
            fuzzy_score=None,
        )
        post_data = PostOpenAIData(
            filter_result=FilterResult(
                candidates=[],
                total_before_filter=0,
                total_after_filter=0,
                filters_applied=[],
                soft_filtering_used=False,
            ),
            ranking_result=RankingResult(results=[], total_results=0),
            retrieval_candidates=[],
            instructor_rows=[],
            distance_meters={},
            text_latency_ms=0,
            vector_latency_ms=0,
            filter_latency_ms=0,
            rank_latency_ms=0,
            vector_search_used=False,
            total_candidates=0,
            filter_failed=False,
            ranking_failed=False,
            skip_vector=False,
        )

        with (
            patch.object(service, "_run_pre_openai_burst", return_value=pre_data),
            patch.object(
                service,
                "_embed_query_with_timeout",
                new_callable=AsyncMock,
                return_value=(None, 5, "embedding_service_unavailable"),
            ),
            patch.object(service, "_run_post_openai_burst", return_value=post_data),
            patch.object(
                service, "_hydrate_instructor_results", new_callable=AsyncMock
            ) as mock_hydrate,
            patch("app.services.search.nl_search_service.record_search_metrics"),
        ):
            mock_hydrate.return_value = sample_instructor_results

            response = await service.search("piano lessons", user_location=(-73.95, 40.68))

        assert isinstance(response, NLSearchResponse)
        assert response.meta.degraded is True
        assert "embedding_service_unavailable" in response.meta.degradation_reasons
        assert len(response.results) == 2
        mock_search_cache.cache_response.assert_awaited_once()
        _, kwargs = mock_search_cache.cache_response.call_args
        assert kwargs.get("ttl") == 30

    @pytest.mark.asyncio
    async def test_handles_parsing_failure(
        self, mock_search_cache: Mock, sample_parsed_query: ParsedQuery
    ) -> None:
        """Should fall back to regex parser and mark degraded."""
        service = NLSearchService(search_cache=mock_search_cache)
        metrics = SearchMetrics()

        with (
            patch(
                "app.services.search.nl_search_service.hybrid_parse",
                new_callable=AsyncMock,
            ) as mock_hybrid_parse,
            patch("app.services.search.nl_search_service.QueryParser") as mock_parser_cls,
            patch("app.services.search.nl_search_service.get_db_session") as mock_session_ctx,
        ):
            mock_hybrid_parse.side_effect = Exception("Parse error")
            mock_parser_cls.return_value.parse.return_value = sample_parsed_query
            mock_session_ctx.return_value.__enter__.return_value = Mock()

            parsed = await service._parse_query("piano", metrics)

            assert parsed == sample_parsed_query
            assert metrics.degraded is True
            assert "parsing_error" in metrics.degradation_reasons


class TestLocationHandling:
    """Tests for location parameter handling."""

    @pytest.mark.asyncio
    async def test_passes_location_to_filter(
        self,
        mock_search_cache: Mock,
        sample_parsed_query: ParsedQuery,
    ) -> None:
        """Should pass location through the pipeline."""
        mock_search_cache.get_cached_response.return_value = None
        mock_search_cache.get_cached_parsed_query.return_value = None

        service = NLSearchService(search_cache=mock_search_cache)
        pre_data = PreOpenAIData(
            parsed_query=sample_parsed_query,
            parse_latency_ms=5,
            text_results={},
            text_latency_ms=0,
            has_service_embeddings=True,
            best_text_score=0.0,
            require_text_match=False,
            skip_vector=False,
            region_lookup=None,
            location_resolution=ResolvedLocation.from_not_found(),
            location_normalized=None,
            cached_alias_normalized=None,
            fuzzy_score=None,
        )
        post_data = PostOpenAIData(
            filter_result=FilterResult(
                candidates=[],
                total_before_filter=0,
                total_after_filter=0,
                filters_applied=[],
                soft_filtering_used=False,
            ),
            ranking_result=RankingResult(results=[], total_results=0),
            retrieval_candidates=[],
            instructor_rows=[],
            distance_meters={},
            text_latency_ms=0,
            vector_latency_ms=0,
            filter_latency_ms=0,
            rank_latency_ms=0,
            vector_search_used=True,
            total_candidates=0,
            filter_failed=False,
            ranking_failed=False,
            skip_vector=False,
        )

        with (
            patch.object(service, "_run_pre_openai_burst", return_value=pre_data),
            patch.object(service, "_embed_query_with_timeout", new_callable=AsyncMock, return_value=([0.1], 5, None)),
            patch.object(service, "_run_post_openai_burst", return_value=post_data) as mock_post,
            patch.object(
                service, "_hydrate_instructor_results", new_callable=AsyncMock
            ) as mock_hydrate,
            patch("app.services.search.nl_search_service.record_search_metrics"),
        ):
            mock_hydrate.return_value = []

            user_location = (-73.95, 40.68)  # Brooklyn
            await service.search("piano", user_location=user_location)

            assert mock_post.call_args.args[6] == user_location


class TestResponseCaching:
    """Tests for response caching."""

    @pytest.mark.asyncio
    async def test_caches_response(
        self,
        mock_search_cache: Mock,
        sample_parsed_query: ParsedQuery,
        sample_instructor_results: List[NLSearchResultItem],
    ) -> None:
        """Should cache response after building."""
        service = NLSearchService(search_cache=mock_search_cache)
        metrics = SearchMetrics()

        response = service._build_instructor_response(
            "piano",
            sample_parsed_query,
            sample_instructor_results,
            limit=20,
            metrics=metrics,
        )

        await service._cache_response("piano", None, response, limit=20)

        mock_search_cache.cache_response.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handles_cache_error(
        self,
        mock_search_cache: Mock,
        sample_parsed_query: ParsedQuery,
        sample_instructor_results: List[NLSearchResultItem],
    ) -> None:
        """Should handle cache error gracefully."""
        mock_search_cache.cache_response.side_effect = Exception("Cache error")

        service = NLSearchService(search_cache=mock_search_cache)
        metrics = SearchMetrics()

        response = service._build_instructor_response(
            "piano",
            sample_parsed_query,
            sample_instructor_results,
            limit=20,
            metrics=metrics,
        )

        # Should not raise
        await service._cache_response("piano", None, response, limit=20)
