# backend/tests/unit/services/search/test_filter_service.py
"""
Unit tests for constraint filtering service.
"""
from datetime import date, time, timedelta
from unittest.mock import Mock

import pytest

from app.services.search.filter_service import (
    MIN_RESULTS_BEFORE_SOFT_FILTER,
    SOFT_PRICE_MULTIPLIER,
    FilteredCandidate,
    FilterService,
)
from app.services.search.location_resolver import ResolutionTier, ResolvedLocation
from app.services.search.query_parser import ParsedQuery
from app.services.search.retriever import ServiceCandidate


@pytest.fixture
def mock_db() -> Mock:
    """Create mock database session."""
    return Mock()


@pytest.fixture
def mock_repository() -> Mock:
    """Create mock filter repository."""
    repo = Mock()

    # Default location behavior - return ALL instructors to avoid soft filtering
    repo.filter_by_location.return_value = [
        "inst_001",
        "inst_002",
        "inst_003",
        "inst_004",
        "inst_005",
        "inst_006",
    ]
    repo.filter_by_location_soft.return_value = [
        "inst_001",
        "inst_002",
        "inst_003",
        "inst_004",
        "inst_005",
        "inst_006",
    ]
    repo.filter_by_region_coverage.return_value = [
        "inst_001",
        "inst_002",
        "inst_003",
        "inst_004",
        "inst_005",
        "inst_006",
    ]
    repo.filter_by_parent_region.return_value = [
        "inst_001",
        "inst_002",
        "inst_003",
        "inst_004",
        "inst_005",
        "inst_006",
    ]

    # Default availability behavior - return ALL instructors
    today = date.today()
    repo.filter_by_availability.return_value = {
        "inst_001": [today, today + timedelta(days=1)],
        "inst_002": [today + timedelta(days=2)],
        "inst_003": [today],
        "inst_004": [today + timedelta(days=1)],
        "inst_005": [today + timedelta(days=3)],
        "inst_006": [today],
    }
    repo.check_weekend_availability.return_value = {
        "inst_001": [today],
        "inst_002": [today],
        "inst_003": [today],
        "inst_004": [today],
        "inst_005": [today],
    }

    return repo


@pytest.fixture
def filter_service(mock_db: Mock, mock_repository: Mock) -> FilterService:
    """Create filter service with mocks."""
    service = FilterService(db=mock_db, repository=mock_repository, region_code="nyc")
    service.location_resolver = Mock()
    service.location_resolver.resolve.return_value = ResolvedLocation.from_not_found()
    return service


@pytest.fixture
def sample_candidates() -> list[ServiceCandidate]:
    """Create sample candidates for testing - 6 candidates to avoid soft filtering."""
    return [
        ServiceCandidate(
            service_id="svc_001",
            service_catalog_id="cat_001",
            hybrid_score=0.95,
            vector_score=0.95,
            text_score=0.90,
            name="Piano Lessons",
            description="Learn piano",
            price_per_hour=50,
            instructor_id="inst_001",
        ),
        ServiceCandidate(
            service_id="svc_002",
            service_catalog_id="cat_002",
            hybrid_score=0.85,
            vector_score=0.80,
            text_score=0.85,
            name="Guitar Lessons",
            description="Learn guitar",
            price_per_hour=55,
            instructor_id="inst_002",
        ),
        ServiceCandidate(
            service_id="svc_003",
            service_catalog_id="cat_003",
            hybrid_score=0.75,
            vector_score=0.70,
            text_score=0.75,
            name="Violin Lessons",
            description="Learn violin",
            price_per_hour=60,
            instructor_id="inst_003",
        ),
        ServiceCandidate(
            service_id="svc_004",
            service_catalog_id="cat_004",
            hybrid_score=0.65,
            vector_score=0.60,
            text_score=0.65,
            name="Drum Lessons",
            description="Learn drums",
            price_per_hour=65,
            instructor_id="inst_004",
        ),
        ServiceCandidate(
            service_id="svc_005",
            service_catalog_id="cat_005",
            hybrid_score=0.55,
            vector_score=0.50,
            text_score=0.55,
            name="Flute Lessons",
            description="Learn flute",
            price_per_hour=70,
            instructor_id="inst_005",
        ),
        ServiceCandidate(
            service_id="svc_006",
            service_catalog_id="cat_006",
            hybrid_score=0.45,
            vector_score=0.40,
            text_score=0.45,
            name="Cello Lessons",
            description="Learn cello",
            price_per_hour=80,
            instructor_id="inst_006",
        ),
    ]


@pytest.fixture
def basic_parsed_query() -> ParsedQuery:
    """Create basic parsed query without constraints."""
    return ParsedQuery(
        original_query="piano lessons",
        service_query="piano lessons",
        parsing_mode="regex",
    )


class TestPriceFilter:
    """Tests for price filtering."""

    @pytest.mark.asyncio
    async def test_price_filter_removes_over_budget(
        self,
        filter_service: FilterService,
        sample_candidates: list[ServiceCandidate],
    ) -> None:
        """Should remove candidates over max price (when enough pass)."""
        # Price limit of 70 allows 5 candidates: $50, $55, $60, $65, $70
        query = ParsedQuery(
            original_query="piano under $70",
            service_query="piano",
            parsing_mode="regex",
            max_price=70,
        )

        result = await filter_service.filter_candidates(sample_candidates, query)

        # 5 candidates should pass, no soft filtering triggered
        prices = [c.price_per_hour for c in result.candidates]
        assert all(p <= 70 for p in prices)
        assert len(result.candidates) == 5
        assert "price" in result.filters_applied
        assert result.soft_filtering_used is False

    @pytest.mark.asyncio
    async def test_no_price_filter_when_not_specified(
        self,
        filter_service: FilterService,
        sample_candidates: list[ServiceCandidate],
        basic_parsed_query: ParsedQuery,
    ) -> None:
        """Should not apply price filter when max_price is None."""
        result = await filter_service.filter_candidates(
            sample_candidates, basic_parsed_query
        )

        assert "price" not in result.filters_applied
        # All candidates should be present (no price filtering)
        assert result.total_before_filter == 6

    @pytest.mark.asyncio
    async def test_price_filter_marks_passed_price(
        self,
        filter_service: FilterService,
        sample_candidates: list[ServiceCandidate],
    ) -> None:
        """Should mark passed_price correctly on candidates."""
        # Allow all prices up to $70 (5 pass, no soft filtering)
        query = ParsedQuery(
            original_query="lessons under $70",
            service_query="lessons",
            parsing_mode="regex",
            max_price=70,
        )

        result = await filter_service.filter_candidates(sample_candidates, query)

        for c in result.candidates:
            assert c.passed_price is True
            assert c.price_per_hour <= 70


class TestLocationFilter:
    """Tests for PostGIS location filtering."""

    @pytest.mark.asyncio
    async def test_location_filter_uses_repository(
        self,
        filter_service: FilterService,
        sample_candidates: list[ServiceCandidate],
        mock_repository: Mock,
    ) -> None:
        """Should call repository for location filtering."""
        filter_service.location_resolver.resolve.return_value = ResolvedLocation.from_borough(
            borough="Manhattan",
            tier=ResolutionTier.EXACT,
            confidence=1.0,
        )
        query = ParsedQuery(
            original_query="piano in Manhattan",
            service_query="piano",
            parsing_mode="regex",
            location_text="Manhattan",
            location_type="neighborhood",
        )

        result = await filter_service.filter_candidates(sample_candidates, query)

        assert mock_repository.filter_by_parent_region.called
        assert "location" in result.filters_applied

    @pytest.mark.asyncio
    async def test_location_filter_removes_non_matching(
        self,
        filter_service: FilterService,
        sample_candidates: list[ServiceCandidate],
        mock_repository: Mock,
    ) -> None:
        """Should remove candidates not in service area (when enough pass)."""
        # Return 5 instructors to avoid soft filtering
        mock_repository.filter_by_parent_region.return_value = [
            "inst_001",
            "inst_002",
            "inst_003",
            "inst_004",
            "inst_005",
        ]
        filter_service.location_resolver.resolve.return_value = ResolvedLocation.from_borough(
            borough="Brooklyn",
            tier=ResolutionTier.EXACT,
            confidence=1.0,
        )

        query = ParsedQuery(
            original_query="piano in Brooklyn",
            service_query="piano",
            parsing_mode="regex",
            location_text="Brooklyn",
            location_type="borough",
        )

        result = await filter_service.filter_candidates(sample_candidates, query)

        # Only the 5 passing instructors should be in results
        instructor_ids = {c.instructor_id for c in result.candidates}
        assert "inst_006" not in instructor_ids
        assert "location" in result.filters_applied
        assert result.soft_filtering_used is False

    @pytest.mark.asyncio
    async def test_location_filter_ambiguous_applies_union(
        self,
        filter_service: FilterService,
        sample_candidates: list[ServiceCandidate],
        mock_repository: Mock,
    ) -> None:
        """Ambiguous locations should still apply a union filter across candidate regions."""
        mock_repository.filter_by_any_region_coverage.return_value = [
            "inst_001",
            "inst_002",
            "inst_003",
            "inst_004",
            "inst_005",
        ]
        filter_service.location_resolver.resolve.return_value = ResolvedLocation.from_ambiguous(
            candidates=[
                {
                    "region_id": "reg_001",
                    "region_name": "Upper East Side",
                    "borough": "Manhattan",
                },
                {
                    "region_id": "reg_002",
                    "region_name": "Upper East Side-Carnegie Hill",
                    "borough": "Manhattan",
                },
            ],
            tier=ResolutionTier.ALIAS,
            confidence=1.0,
        )

        query = ParsedQuery(
            original_query="piano lessons in ues",
            service_query="piano lessons",
            parsing_mode="regex",
            location_text="ues",
            location_type="neighborhood",
        )

        result = await filter_service.filter_candidates(sample_candidates, query)

        assert mock_repository.filter_by_any_region_coverage.called
        assert "location" in result.filters_applied
        assert result.filter_stats.get("after_location") == 5
        assert result.soft_filtering_used is False

    @pytest.mark.asyncio
    async def test_location_filter_skipped_for_near_me(
        self,
        filter_service: FilterService,
        sample_candidates: list[ServiceCandidate],
        mock_repository: Mock,
    ) -> None:
        """Should skip location filter for 'near me' without user location."""
        query = ParsedQuery(
            original_query="piano near me",
            service_query="piano",
            parsing_mode="regex",
            location_text="near me",
            location_type="near_me",
        )

        result = await filter_service.filter_candidates(sample_candidates, query)

        # Location filter should not be applied without user coords
        mock_repository.filter_by_location.assert_not_called()
        mock_repository.filter_by_parent_region.assert_not_called()
        mock_repository.filter_by_region_coverage.assert_not_called()
        filter_service.location_resolver.resolve.assert_not_called()
        assert "location" not in result.filters_applied

    @pytest.mark.asyncio
    async def test_location_filter_with_user_location(
        self,
        filter_service: FilterService,
        sample_candidates: list[ServiceCandidate],
        mock_repository: Mock,
    ) -> None:
        """Should use provided user location."""
        query = ParsedQuery(
            original_query="piano",
            service_query="piano",
            parsing_mode="regex",
        )
        user_location = (-73.99, 40.73)

        await filter_service.filter_candidates(
            sample_candidates, query, user_location=user_location
        )

        # filter_by_location should be called with the user coordinates
        mock_repository.filter_by_location.assert_called()
        # Check first call args
        call_args = mock_repository.filter_by_location.call_args_list[0]
        assert call_args[0][1] == -73.99  # lng
        assert call_args[0][2] == 40.73  # lat


class TestAvailabilityFilter:
    """Tests for availability filtering."""

    @pytest.mark.asyncio
    async def test_availability_filter_with_specific_date(
        self,
        filter_service: FilterService,
        sample_candidates: list[ServiceCandidate],
        mock_repository: Mock,
    ) -> None:
        """Should filter by specific date."""
        target_date = date.today() + timedelta(days=1)
        query = ParsedQuery(
            original_query="piano tomorrow",
            service_query="piano",
            parsing_mode="regex",
            date=target_date,
            date_type="specific",
        )

        result = await filter_service.filter_candidates(sample_candidates, query)

        mock_repository.filter_by_availability.assert_called()
        assert "availability" in result.filters_applied

    @pytest.mark.asyncio
    async def test_availability_filter_with_time_constraints(
        self,
        filter_service: FilterService,
        sample_candidates: list[ServiceCandidate],
        mock_repository: Mock,
    ) -> None:
        """Should pass time constraints to repository."""
        query = ParsedQuery(
            original_query="piano after 5pm",
            service_query="piano",
            parsing_mode="regex",
            time_after="17:00",
        )

        await filter_service.filter_candidates(sample_candidates, query)

        mock_repository.filter_by_availability.assert_called()
        # Check the time_after was parsed and passed as keyword arg
        call_args = mock_repository.filter_by_availability.call_args_list[0]
        # Method called with keyword arguments
        assert call_args.kwargs.get("time_after") == time(17, 0)

    @pytest.mark.asyncio
    async def test_availability_filter_weekend(
        self,
        filter_service: FilterService,
        sample_candidates: list[ServiceCandidate],
        mock_repository: Mock,
    ) -> None:
        """Should use weekend availability check for weekend queries."""
        saturday = date(2024, 1, 6)
        sunday = date(2024, 1, 7)
        query = ParsedQuery(
            original_query="piano this weekend",
            service_query="piano",
            parsing_mode="regex",
            date_type="weekend",
            date_range_start=saturday,
            date_range_end=sunday,
        )

        await filter_service.filter_candidates(sample_candidates, query)

        mock_repository.check_weekend_availability.assert_called()

    @pytest.mark.asyncio
    async def test_availability_sets_available_dates(
        self,
        filter_service: FilterService,
        sample_candidates: list[ServiceCandidate],
        mock_repository: Mock,
    ) -> None:
        """Should set available_dates on candidates."""
        today = date.today()
        mock_repository.filter_by_availability.return_value = {
            "inst_001": [today, today + timedelta(days=1)],
            "inst_002": [today],
            "inst_003": [today],
            "inst_004": [today],
            "inst_005": [today],
        }

        query = ParsedQuery(
            original_query="piano",
            service_query="piano",
            parsing_mode="regex",
            date=today,
        )

        result = await filter_service.filter_candidates(sample_candidates, query)

        matching = [c for c in result.candidates if c.instructor_id == "inst_001"]
        if matching:
            assert len(matching[0].available_dates) == 2
            assert matching[0].earliest_available == today


class TestSoftFiltering:
    """Tests for soft filtering fallback."""

    @pytest.mark.asyncio
    async def test_soft_filtering_triggered_when_few_results(
        self,
        filter_service: FilterService,
        mock_repository: Mock,
    ) -> None:
        """Should trigger soft filtering when < 5 results."""
        filter_service.location_resolver.resolve.return_value = ResolvedLocation.from_borough(
            borough="Manhattan",
            tier=ResolutionTier.EXACT,
            confidence=1.0,
        )
        # Only return 2 instructors from hard location filter
        mock_repository.filter_by_parent_region.return_value = ["inst_001", "inst_002"]
        today = date.today()
        mock_repository.filter_by_availability.return_value = {
            "inst_001": [today],
            "inst_002": [today],
            "inst_003": [today],
        }

        candidates = [
            ServiceCandidate(
                service_id=f"svc_{i}",
                service_catalog_id=f"cat_{i}",
                hybrid_score=0.9 - i * 0.1,
                vector_score=0.9 - i * 0.1,
                text_score=None,
                name=f"Lesson {i}",
                description=None,
                price_per_hour=50 + i * 10,
                instructor_id=f"inst_00{i+1}",
            )
            for i in range(5)
        ]

        query = ParsedQuery(
            original_query="piano in Manhattan",
            service_query="piano",
            parsing_mode="regex",
            location_text="Manhattan",
        )

        result = await filter_service.filter_candidates(candidates, query)

        # Should have triggered soft filtering since only 2 passed hard filter
        assert result.soft_filtering_used is True

    @pytest.mark.asyncio
    async def test_soft_filtering_relaxes_price(
        self,
        mock_db: Mock,
        mock_repository: Mock,
    ) -> None:
        """Soft filtering should allow 1.25x price."""
        today = date.today()
        mock_repository.filter_by_availability.return_value = {
            "inst_001": [today],
        }

        # Single candidate over budget but within soft range
        candidates = [
            ServiceCandidate(
                service_id="svc_001",
                service_catalog_id="cat_001",
                hybrid_score=0.9,
                vector_score=0.9,
                text_score=None,
                name="Test",
                description=None,
                price_per_hour=70,  # Over $60 but under $75 (60 * 1.25)
                instructor_id="inst_001",
            ),
        ]

        query = ParsedQuery(
            original_query="lessons under $60",
            service_query="lessons",
            parsing_mode="regex",
            max_price=60,
        )

        service = FilterService(db=mock_db, repository=mock_repository)
        result = await service.filter_candidates(candidates, query)

        # Should include $70 candidate with soft filtering
        assert result.soft_filtering_used is True
        assert len(result.candidates) > 0
        assert any("price_relaxed" in c.soft_filter_reasons for c in result.candidates)

    @pytest.mark.asyncio
    async def test_soft_filtering_applies_score_penalty(
        self,
        mock_db: Mock,
        mock_repository: Mock,
    ) -> None:
        """Soft-filtered candidates should have 0.7x score penalty."""
        today = date.today()
        mock_repository.filter_by_availability.return_value = {
            "inst_001": [today],
        }

        candidates = [
            ServiceCandidate(
                service_id="svc_001",
                service_catalog_id="cat_001",
                hybrid_score=1.0,
                vector_score=1.0,
                text_score=None,
                name="Test",
                description=None,
                price_per_hour=70,  # Over budget but within soft range
                instructor_id="inst_001",
            ),
        ]

        query = ParsedQuery(
            original_query="lessons under $60",
            service_query="lessons",
            parsing_mode="regex",
            max_price=60,
        )

        service = FilterService(db=mock_db, repository=mock_repository)
        result = await service.filter_candidates(candidates, query)

        if result.candidates and result.candidates[0].soft_filter_reasons:
            # Score should be penalized
            assert result.candidates[0].hybrid_score == pytest.approx(0.7, abs=0.01)


class TestFilterResult:
    """Tests for FilterResult dataclass."""

    @pytest.mark.asyncio
    async def test_filter_result_counts(
        self,
        filter_service: FilterService,
        sample_candidates: list[ServiceCandidate],
    ) -> None:
        """Should track before/after counts correctly."""
        query = ParsedQuery(
            original_query="lessons under $70",
            service_query="lessons",
            parsing_mode="regex",
            max_price=70,
        )

        result = await filter_service.filter_candidates(sample_candidates, query)

        assert result.total_before_filter == 6
        assert result.total_after_filter <= 6
        assert len(result.candidates) == result.total_after_filter

    @pytest.mark.asyncio
    async def test_filter_result_tracks_applied_filters(
        self,
        filter_service: FilterService,
        sample_candidates: list[ServiceCandidate],
        mock_repository: Mock,
    ) -> None:
        """Should track which filters were applied."""
        filter_service.location_resolver.resolve.return_value = ResolvedLocation.from_borough(
            borough="Brooklyn",
            tier=ResolutionTier.EXACT,
            confidence=1.0,
        )
        query = ParsedQuery(
            original_query="piano in Brooklyn under $80 tomorrow",
            service_query="piano",
            parsing_mode="regex",
            max_price=80,
            location_text="Brooklyn",
            date=date.today() + timedelta(days=1),
        )

        result = await filter_service.filter_candidates(sample_candidates, query)

        assert "price" in result.filters_applied
        assert "location" in result.filters_applied
        assert "availability" in result.filters_applied


class TestEdgeCases:
    """Tests for edge cases."""

    @pytest.mark.asyncio
    async def test_empty_candidates(
        self,
        filter_service: FilterService,
        basic_parsed_query: ParsedQuery,
    ) -> None:
        """Should handle empty candidate list."""
        result = await filter_service.filter_candidates([], basic_parsed_query)

        assert result.candidates == []
        assert result.total_before_filter == 0
        assert result.total_after_filter == 0

    @pytest.mark.asyncio
    async def test_no_filters_applied(
        self,
        filter_service: FilterService,
        sample_candidates: list[ServiceCandidate],
        basic_parsed_query: ParsedQuery,
    ) -> None:
        """Should return all candidates when no filters specified."""
        result = await filter_service.filter_candidates(
            sample_candidates, basic_parsed_query
        )

        assert result.total_before_filter == result.total_after_filter
        assert result.filters_applied == []

    @pytest.mark.asyncio
    async def test_location_not_found(
        self,
        filter_service: FilterService,
        sample_candidates: list[ServiceCandidate],
        mock_repository: Mock,
    ) -> None:
        """Should skip location filter when location not found."""
        filter_service.location_resolver.resolve.return_value = ResolvedLocation.from_not_found()

        query = ParsedQuery(
            original_query="piano in Narnia",
            service_query="piano",
            parsing_mode="regex",
            location_text="Narnia",
        )

        result = await filter_service.filter_candidates(sample_candidates, query)

        # Location filter should not be in applied filters
        assert "location" not in result.filters_applied
        # But the funnel should still expose after_location for observability
        assert result.filter_stats.get("after_location") == len(sample_candidates)

    @pytest.mark.asyncio
    async def test_invalid_time_format(
        self,
        filter_service: FilterService,
        sample_candidates: list[ServiceCandidate],
    ) -> None:
        """Should handle invalid time format gracefully."""
        query = ParsedQuery(
            original_query="piano at noon",
            service_query="piano",
            parsing_mode="regex",
            time_after="invalid",  # Invalid format
        )

        # Should not raise, just ignore the time constraint
        result = await filter_service.filter_candidates(sample_candidates, query)
        assert result is not None


class TestFilteredCandidate:
    """Tests for FilteredCandidate dataclass."""

    def test_filtered_candidate_creation(self) -> None:
        """Should create filtered candidate with all fields."""
        candidate = FilteredCandidate(
            service_id="svc_001",
            service_catalog_id="cat_001",
            instructor_id="inst_001",
            hybrid_score=0.85,
            name="Piano Lessons",
            description="Learn piano",
            price_per_hour=50,
        )

        assert candidate.service_id == "svc_001"
        assert candidate.instructor_id == "inst_001"
        assert candidate.hybrid_score == 0.85
        assert candidate.passed_price is True
        assert candidate.passed_location is True
        assert candidate.passed_availability is True
        assert candidate.soft_filtered is False
        assert candidate.soft_filter_reasons == []
        assert candidate.available_dates == []
        assert candidate.earliest_available is None

    def test_filtered_candidate_with_soft_filter(self) -> None:
        """Should track soft filter reasons."""
        candidate = FilteredCandidate(
            service_id="svc_001",
            service_catalog_id="cat_001",
            instructor_id="inst_001",
            hybrid_score=0.85,
            name="Piano Lessons",
            description=None,
            price_per_hour=70,
            soft_filtered=True,
            soft_filter_reasons=["price_relaxed"],
        )

        assert candidate.soft_filtered is True
        assert "price_relaxed" in candidate.soft_filter_reasons


class TestConstants:
    """Tests for filter service constants."""

    def test_min_results_threshold(self) -> None:
        """MIN_RESULTS_BEFORE_SOFT_FILTER should be reasonable."""
        assert 3 <= MIN_RESULTS_BEFORE_SOFT_FILTER <= 10

    def test_soft_price_multiplier(self) -> None:
        """SOFT_PRICE_MULTIPLIER should be > 1.0."""
        assert SOFT_PRICE_MULTIPLIER > 1.0
        assert SOFT_PRICE_MULTIPLIER <= 1.5  # Not too generous
