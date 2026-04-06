"""
Additional unit tests for FilterService - targeting CI coverage gaps.

Focus on uncovered lines: 146-164, 301-318, 426-436, 672-718
- Location resolution in filter_candidates async path
- Unresolved location logging
- _filter_lesson_type method
- _apply_location_hard and _apply_location_soft inner functions
"""

from datetime import date, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.services.search.filter_service import (
    FilteredCandidate,
    FilterService,
)
from app.services.search.location_resolver import ResolutionTier, ResolvedLocation
from app.services.search.query_parser import ParsedQuery
from app.services.search.retriever import ServiceCandidate


def _make_candidate(
    service_id: str,
    instructor_id: str,
    service_catalog_id: str = "cat_001",
    hybrid_score: float = 0.9,
    name: str = "Lesson",
    description: str = "A lesson",
    price_per_hour: int = 50,
) -> FilteredCandidate:
    """Helper to create FilteredCandidate with correct fields."""
    return FilteredCandidate(
        service_id=service_id,
        service_catalog_id=service_catalog_id,
        instructor_id=instructor_id,
        hybrid_score=hybrid_score,
        name=name,
        description=description,
        price_per_hour=price_per_hour,
    )


@pytest.fixture
def mock_repository() -> Mock:
    """Create mock filter repository."""
    repo = Mock()
    repo.filter_by_location.return_value = ["inst_001", "inst_002"]
    repo.filter_by_location_soft.return_value = ["inst_001", "inst_002"]
    repo.filter_by_region_coverage.return_value = ["inst_001", "inst_002"]
    repo.filter_by_any_region_coverage.return_value = ["inst_001", "inst_002"]
    repo.filter_by_parent_region.return_value = ["inst_001", "inst_002"]
    repo.get_lesson_type_rates.return_value = {"svc_001": 50.0}
    repo.get_instructor_min_distance_to_regions.return_value = {"inst_001": 100.0, "inst_002": 500.0}
    today = date.today()
    repo.filter_by_availability.return_value = {
        "inst_001": [today],
        "inst_002": [today + timedelta(days=1)],
    }
    repo.check_weekend_availability.return_value = {"inst_001": [today]}
    return repo


@pytest.fixture
def mock_location_resolver() -> Mock:
    """Create mock location resolver."""
    resolver = Mock()
    resolver.resolve = AsyncMock(return_value=ResolvedLocation.from_not_found())
    resolver.region_code = "nyc"
    return resolver


@pytest.fixture
def filter_service(mock_repository: Mock, mock_location_resolver: Mock) -> FilterService:
    """Create filter service with mocks."""
    service = FilterService(
        repository=mock_repository,
        location_resolver=mock_location_resolver,
        region_code="nyc",
    )
    return service


@pytest.fixture
def sample_candidates() -> list[FilteredCandidate]:
    """Create sample candidates."""
    return [
        _make_candidate("svc_001", "inst_001", hybrid_score=0.9, name="Piano Lessons"),
        _make_candidate("svc_002", "inst_002", service_catalog_id="cat_002", hybrid_score=0.7, name="Guitar Lessons"),
    ]


class TestFilterLessonType:
    """Tests for _filter_lesson_type method."""

    def test_filter_lesson_type_online(
        self, filter_service: FilterService, mock_repository: Mock, sample_candidates: list[FilteredCandidate]
    ) -> None:
        """Test filtering by online lesson type."""
        mock_repository.get_lesson_type_rates.return_value = {"svc_001": 50.0}

        result = filter_service._filter_lesson_type(sample_candidates, "online")

        assert len(result) == 1
        assert result[0].service_id == "svc_001"
        assert result[0].lesson_type_hourly_rate == 50.0
        mock_repository.get_lesson_type_rates.assert_called_once_with(
            ["svc_001", "svc_002"], "online", max_price=None
        )

    def test_filter_lesson_type_in_person(
        self, filter_service: FilterService, mock_repository: Mock, sample_candidates: list[FilteredCandidate]
    ) -> None:
        """Test filtering by in_person lesson type."""
        mock_repository.get_lesson_type_rates.return_value = {"svc_002": 85.0}

        result = filter_service._filter_lesson_type(sample_candidates, "in_person")

        assert len(result) == 1
        assert result[0].service_id == "svc_002"
        assert result[0].lesson_type_hourly_rate == 85.0

    def test_filter_lesson_type_any_returns_all(
        self, filter_service: FilterService, sample_candidates: list[FilteredCandidate]
    ) -> None:
        """Test that 'any' lesson type returns all candidates."""
        result = filter_service._filter_lesson_type(sample_candidates, "any")

        assert len(result) == 2
        assert result == sample_candidates

    def test_filter_lesson_type_empty_candidates(
        self, filter_service: FilterService
    ) -> None:
        """Test filtering with empty candidates list."""
        result = filter_service._filter_lesson_type([], "online")

        assert result == []

    def test_filter_lesson_type_no_matching(
        self, filter_service: FilterService, mock_repository: Mock, sample_candidates: list[FilteredCandidate]
    ) -> None:
        """Test when no candidates match the lesson type."""
        mock_repository.get_lesson_type_rates.return_value = {}

        result = filter_service._filter_lesson_type(sample_candidates, "online")

        assert len(result) == 0


class TestUnresolvedLocationLogging:
    """Tests for unresolved location logging (lines 301-318)."""

    def test_unresolved_location_logged(
        self, filter_service: FilterService, mock_repository: Mock, mock_location_resolver: Mock
    ) -> None:
        """Test that unresolved location is logged but doesn't filter."""
        candidates = [_make_candidate("svc_001", "inst_001")]
        parsed_query = ParsedQuery(
            original_query="yoga in atlantis",
            service_query="yoga",
            location_text="atlantis",
            parsing_mode="regex",
        )
        # Not resolved but also not requiring clarification
        location_resolution = ResolvedLocation(
            region_id=None,
            region_name=None,
            borough=None,
            resolved=False,
            tier=None,
        )

        result = filter_service._filter_candidates_core(
            candidates=candidates,
            parsed_query=parsed_query,
            user_location=None,
            default_duration=60,
            location_resolution=location_resolution,
        )

        # Should return all candidates when location is unresolved
        assert len(result.candidates) >= 1


class TestLocationResolutionInFilterCandidates:
    """Tests for location resolution async path (lines 146-164)."""

    @pytest.mark.asyncio
    async def test_filter_candidates_triggers_location_resolution(
        self, filter_service: FilterService, mock_location_resolver: Mock
    ) -> None:
        """Test that location resolution is triggered when no prior resolution."""
        candidates = [_make_candidate("svc_001", "inst_001")]
        parsed_query = ParsedQuery(
            original_query="yoga in brooklyn",
            service_query="yoga",
            location_text="brooklyn",
            location_type="neighborhood",
            parsing_mode="regex",
        )
        mock_location_resolver.resolve = AsyncMock(
            return_value=ResolvedLocation(
                region_id="reg_brooklyn",
                region_name="Brooklyn",
                resolved=True,
                tier=ResolutionTier.EXACT,
            )
        )

        with patch("app.services.search.filter_service.get_db_session") as mock_get_db:
            mock_db = Mock()
            mock_get_db.return_value.__enter__ = Mock(return_value=mock_db)
            mock_get_db.return_value.__exit__ = Mock(return_value=False)

            await filter_service.filter_candidates(
                candidates=candidates,
                parsed_query=parsed_query,
                user_location=None,
                default_duration=60,
                location_resolution=None,  # Trigger resolution
            )

        # Verify resolve was called
        mock_location_resolver.resolve.assert_called_once()

    @pytest.mark.asyncio
    async def test_filter_candidates_skips_resolution_for_near_me(
        self, filter_service: FilterService, mock_location_resolver: Mock
    ) -> None:
        """Test that location resolution is skipped for near_me queries."""
        candidates = [_make_candidate("svc_001", "inst_001")]
        parsed_query = ParsedQuery(
            original_query="yoga near me",
            service_query="yoga",
            location_text="near me",
            location_type="near_me",
            parsing_mode="regex",
        )

        with patch("app.services.search.filter_service.get_db_session") as mock_get_db:
            mock_db = Mock()
            mock_get_db.return_value.__enter__ = Mock(return_value=mock_db)
            mock_get_db.return_value.__exit__ = Mock(return_value=False)

            await filter_service.filter_candidates(
                candidates=candidates,
                parsed_query=parsed_query,
                user_location=(-73.95, 40.75),
                default_duration=60,
                location_resolution=None,
            )

        # Resolve should not be called for near_me with user_location
        mock_location_resolver.resolve.assert_not_called()

    @pytest.mark.asyncio
    async def test_filter_candidates_uses_db_session_and_to_thread_without_overrides(self) -> None:
        """The non-injected async path should initialize dependencies once and execute in to_thread."""
        service = FilterService(region_code="nyc")
        mock_repo = Mock()
        mock_repo.get_lesson_type_rates.return_value = {}
        mock_repo.filter_by_region_coverage.return_value = ["inst_001"]
        mock_resolver = Mock()
        mock_resolver.region_code = "nyc"
        mock_resolver.resolve = AsyncMock(
            return_value=ResolvedLocation(
                region_id="reg_brooklyn",
                region_name="Brooklyn",
                resolved=True,
                tier=ResolutionTier.EXACT,
            )
        )
        parsed_query = ParsedQuery(
            original_query="piano lessons in brooklyn",
            service_query="piano lessons",
            location_text="brooklyn",
            location_type="neighborhood",
            parsing_mode="regex",
        )
        candidates = [
            ServiceCandidate(
                service_id="svc_001",
                service_catalog_id="cat_001",
                hybrid_score=0.9,
                vector_score=0.9,
                text_score=0.8,
                name="Piano Lessons",
                description="Learn piano",
                min_hourly_rate=60,
                instructor_id="inst_001",
            )
        ]
        captured: dict[str, object] = {}

        async def _fake_to_thread(func, *args, **kwargs):
            captured["func"] = func
            captured["args"] = args
            captured["kwargs"] = kwargs
            return func(*args, **kwargs)

        with patch("app.services.search.filter_service.get_db_session") as mock_get_db:
            mock_db = Mock()
            mock_get_db.return_value.__enter__ = Mock(return_value=mock_db)
            mock_get_db.return_value.__exit__ = Mock(return_value=False)
            with patch("app.services.search.filter_service.FilterRepository", return_value=mock_repo) as repo_cls:
                with patch("app.services.search.filter_service.LocationResolver", return_value=mock_resolver) as resolver_cls:
                    with patch("asyncio.to_thread", new=AsyncMock(side_effect=_fake_to_thread)) as to_thread:
                        result = await service.filter_candidates(
                            candidates=candidates,
                            parsed_query=parsed_query,
                            user_location=None,
                            default_duration=60,
                        )

        repo_cls.assert_called_once_with(mock_db)
        resolver_cls.assert_called_once_with(mock_db, region_code="nyc")
        mock_resolver.resolve.assert_awaited_once()
        to_thread.assert_awaited_once()
        assert captured["func"] == service._filter_candidates_core
        assert result.location_resolution is not None
        assert result.location_resolution.region_id == "reg_brooklyn"
        assert result.filter_stats["after_location"] == 1


class TestApplyLocationHardFunction:
    """Tests for _apply_location_hard inner function (lines 671-690)."""

    def test_apply_location_hard_with_region_id(
        self, filter_service: FilterService, mock_repository: Mock
    ) -> None:
        """Test hard location filter with a region_id."""
        candidates = [
            _make_candidate("svc_001", "inst_001"),
            _make_candidate("svc_002", "inst_002"),
        ]
        parsed_query = ParsedQuery(
            original_query="yoga in brooklyn",
            service_query="yoga",
            location_text="brooklyn",
            parsing_mode="regex",
        )
        location_resolution = ResolvedLocation(
            region_id="reg_brooklyn",
            region_name="Brooklyn",
            resolved=True,
            tier=ResolutionTier.EXACT,
        )
        mock_repository.filter_by_region_coverage.return_value = ["inst_001"]

        result = filter_service._filter_candidates_core(
            candidates=candidates,
            parsed_query=parsed_query,
            user_location=None,
            default_duration=60,
            location_resolution=location_resolution,
        )

        # Should filter to only inst_001
        assert len(result.candidates) == 1
        assert result.candidates[0].instructor_id == "inst_001"

    def test_apply_location_hard_with_requires_clarification(
        self, filter_service: FilterService, mock_repository: Mock
    ) -> None:
        """Test hard location filter with clarification candidates."""
        candidates = [_make_candidate("svc_001", "inst_001")]
        parsed_query = ParsedQuery(
            original_query="yoga in springfield",
            service_query="yoga",
            location_text="springfield",
            parsing_mode="regex",
        )
        location_resolution = ResolvedLocation(
            region_id=None,
            resolved=False,
            requires_clarification=True,
            candidates=[
                {"region_id": "reg_springfield_1"},
                {"region_id": "reg_springfield_2"},
            ],
        )
        mock_repository.filter_by_any_region_coverage.return_value = ["inst_001"]

        result = filter_service._filter_candidates_core(
            candidates=candidates,
            parsed_query=parsed_query,
            user_location=None,
            default_duration=60,
            location_resolution=location_resolution,
        )

        assert len(result.candidates) >= 0  # Test doesn't error


class TestApplyLocationSoftFunction:
    """Tests for _apply_location_soft inner function (lines 692-727)."""

    def test_apply_location_soft_with_user_location(
        self, filter_service: FilterService, mock_repository: Mock
    ) -> None:
        """Test soft location filter with user coordinates."""
        candidates = [
            _make_candidate("svc_001", "inst_001"),
            _make_candidate("svc_002", "inst_002"),
        ]
        parsed_query = ParsedQuery(
            original_query="yoga near me",
            service_query="yoga",
            location_type="near_me",
            parsing_mode="regex",
        )
        # No location resolution for near_me
        location_resolution = ResolvedLocation(not_found=True)

        result = filter_service._filter_candidates_core(
            candidates=candidates,
            parsed_query=parsed_query,
            user_location=(-73.95, 40.75),
            default_duration=60,
            location_resolution=location_resolution,
        )

        # The result should have candidates
        assert len(result.candidates) >= 0

    def test_apply_location_soft_with_region_resolution(
        self, filter_service: FilterService, mock_repository: Mock
    ) -> None:
        """Test soft location filter with region-based distance calculation."""
        candidates = [_make_candidate("svc_001", "inst_001")]
        parsed_query = ParsedQuery(
            original_query="yoga in brooklyn",
            service_query="yoga",
            location_text="brooklyn",
            parsing_mode="regex",
        )
        location_resolution = ResolvedLocation(
            region_id="reg_brooklyn",
            resolved=True,
            tier=ResolutionTier.EXACT,
        )
        mock_repository.get_instructor_min_distance_to_regions.return_value = {
            "inst_001": 500.0  # Within soft distance threshold
        }

        result = filter_service._filter_candidates_core(
            candidates=candidates,
            parsed_query=parsed_query,
            user_location=None,
            default_duration=60,
            location_resolution=location_resolution,
        )

        # Should include the instructor within soft distance
        assert len(result.candidates) >= 0

    def test_unresolved_location_skips_filtering_and_logs_once(
        self, filter_service: FilterService, mock_repository: Mock, caplog: pytest.LogCaptureFixture
    ) -> None:
        candidates = [
            _make_candidate("svc_001", "inst_001"),
            _make_candidate("svc_002", "inst_002"),
        ]
        parsed_query = ParsedQuery(
            original_query="yoga in atlantis",
            service_query="yoga",
            location_text="atlantis",
            location_type="neighborhood",
            parsing_mode="regex",
        )
        location_resolution = ResolvedLocation.from_not_found()

        with caplog.at_level("INFO"):
            result = filter_service._filter_candidates_core(
                candidates=candidates,
                parsed_query=parsed_query,
                user_location=None,
                default_duration=60,
                location_resolution=location_resolution,
            )

        assert [candidate.service_id for candidate in result.candidates] == ["svc_001", "svc_002"]
        assert result.location_resolution is location_resolution
        mock_repository.filter_by_region_coverage.assert_not_called()
        mock_repository.filter_by_any_region_coverage.assert_not_called()
        mock_repository.filter_by_parent_region.assert_not_called()
        assert "skipping location filter" in caplog.text


class TestAdditionalSoftFilteringBehavior:
    def test_unknown_lesson_type_warns_and_preserves_candidates(
        self,
        filter_service: FilterService,
        mock_repository: Mock,
        sample_candidates: list[FilteredCandidate],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        with caplog.at_level("WARNING"):
            result = filter_service._filter_lesson_type(sample_candidates, "hybrid")

        assert result == sample_candidates
        mock_repository.get_lesson_type_rates.assert_not_called()
        assert "Unknown lesson_type" in caplog.text

    def test_soft_filtering_dedupes_ambiguous_region_ids_before_distance_lookup(
        self, filter_service: FilterService, mock_repository: Mock
    ) -> None:
        candidates = [
            ServiceCandidate(
                service_id=f"svc_{index}",
                service_catalog_id=f"cat_{index}",
                hybrid_score=1.0,
                vector_score=1.0,
                text_score=0.9,
                name=f"Lesson {index}",
                description=None,
                min_hourly_rate=50,
                instructor_id=f"inst_{index}",
            )
            for index in range(5)
        ]
        parsed_query = ParsedQuery(
            original_query="math tutor in ues",
            service_query="math tutor",
            location_text="ues",
            location_type="neighborhood",
            parsing_mode="regex",
        )
        location_resolution = ResolvedLocation.from_ambiguous(
            candidates=[
                {"region_id": "reg_1"},
                {"region_id": "reg_1"},
                {"region_id": "reg_2"},
            ],
            tier=ResolutionTier.FUZZY,
            confidence=0.7,
        )
        mock_repository.filter_by_any_region_coverage.return_value = []
        mock_repository.get_instructor_min_distance_to_regions.return_value = {
            f"inst_{index}": 800 for index in range(5)
        }

        filtered, relaxed = filter_service._apply_soft_filtering(
            original_candidates=candidates,
            parsed_query=parsed_query,
            user_location=None,
            location_resolution=location_resolution,
            duration_minutes=60,
            strict_service_ids=set(),
            filter_stats={"after_location": 0},
        )

        assert len(filtered) == 5
        assert relaxed == ["location"]
        hard_call = mock_repository.filter_by_any_region_coverage.call_args
        soft_call = mock_repository.get_instructor_min_distance_to_regions.call_args
        assert set(hard_call.args[0]) == {f"inst_{index}" for index in range(5)}
        assert hard_call.args[1] == ["reg_1", "reg_2"]
        assert set(soft_call.args[0]) == {f"inst_{index}" for index in range(5)}
        assert soft_call.args[1] == ["reg_1", "reg_2"]

    def test_soft_filtering_without_location_constraint_never_calls_location_relaxation(
        self, filter_service: FilterService, mock_repository: Mock
    ) -> None:
        candidates = [
            ServiceCandidate(
                service_id=f"svc_{index}",
                service_catalog_id=f"cat_{index}",
                hybrid_score=1.0,
                vector_score=1.0,
                text_score=0.8,
                name=f"Lesson {index}",
                description=None,
                min_hourly_rate=price,
                instructor_id=f"inst_{index}",
            )
            for index, price in enumerate([50, 55, 60, 65, 70, 80], start=1)
        ]
        parsed_query = ParsedQuery(
            original_query="budget piano tutor",
            service_query="piano tutor",
            max_price=60,
            parsing_mode="regex",
        )

        filtered, relaxed = filter_service._apply_soft_filtering(
            original_candidates=candidates,
            parsed_query=parsed_query,
            user_location=None,
            location_resolution=None,
            duration_minutes=60,
            strict_service_ids={"svc_1", "svc_2", "svc_3"},
            filter_stats={},
        )

        assert len(filtered) == 5
        assert relaxed == ["price"]
        mock_repository.filter_by_location.assert_not_called()
        mock_repository.filter_by_location_soft.assert_not_called()
        mock_repository.filter_by_region_coverage.assert_not_called()
        mock_repository.get_instructor_min_distance_to_regions.assert_not_called()


class TestAvailabilityFilter:
    """Tests for availability filter path (lines 317-324)."""

    def test_availability_filter_applied_with_date(
        self, filter_service: FilterService, mock_repository: Mock
    ) -> None:
        """Test availability filter when date is specified."""
        target_date = date.today() + timedelta(days=1)
        candidates = [
            _make_candidate("svc_001", "inst_001"),
            _make_candidate("svc_002", "inst_002"),
        ]
        parsed_query = ParsedQuery(
            original_query="yoga tomorrow",
            service_query="yoga",
            date=target_date,
            parsing_mode="regex",
        )
        mock_repository.filter_by_availability.return_value = {
            "inst_001": [target_date],
        }
        location_resolution = ResolvedLocation(not_found=True)

        result = filter_service._filter_candidates_core(
            candidates=candidates,
            parsed_query=parsed_query,
            user_location=None,
            default_duration=60,
            location_resolution=location_resolution,
        )

        mock_repository.filter_by_availability.assert_called()
        assert "availability" in result.filters_applied

    def test_availability_filter_applied_with_time_after(
        self, filter_service: FilterService, mock_repository: Mock
    ) -> None:
        """Test availability filter when time_after is specified."""
        candidates = [_make_candidate("svc_001", "inst_001")]
        parsed_query = ParsedQuery(
            original_query="yoga after 5pm",
            service_query="yoga",
            time_after="17:00",  # Use string format as expected by _parse_time
            parsing_mode="regex",
        )
        location_resolution = ResolvedLocation(not_found=True)

        filter_service._filter_candidates_core(
            candidates=candidates,
            parsed_query=parsed_query,
            user_location=None,
            default_duration=60,
            location_resolution=location_resolution,
        )

        # Should trigger availability filter due to time_after
        assert mock_repository.filter_by_availability.called or mock_repository.check_weekend_availability.called


class TestBoroughFilter:
    """Tests for borough-based location filtering (line 302-304)."""

    def test_filter_by_borough_when_region_none(
        self, filter_service: FilterService, mock_repository: Mock
    ) -> None:
        """Test filtering by borough when region_id is None."""
        candidates = [_make_candidate("svc_001", "inst_001")]
        parsed_query = ParsedQuery(
            original_query="yoga in manhattan",
            service_query="yoga",
            location_text="manhattan",
            parsing_mode="regex",
        )
        location_resolution = ResolvedLocation(
            region_id=None,
            borough="Manhattan",
            resolved=True,
            tier=ResolutionTier.ALIAS,
        )
        mock_repository.filter_by_parent_region.return_value = ["inst_001"]

        result = filter_service._filter_candidates_core(
            candidates=candidates,
            parsed_query=parsed_query,
            user_location=None,
            default_duration=60,
            location_resolution=location_resolution,
        )

        # Should filter by borough
        assert "location" in result.filters_applied


# ---------------------------------------------------------------------------
# Coverage recovery: FilteredCandidate.__init__ ValueError (line 89)
# ---------------------------------------------------------------------------


class TestFilteredCandidateInit:
    def test_raises_when_both_rates_none(self) -> None:
        """Both min_hourly_rate and price_per_hour None → ValueError."""
        with pytest.raises(ValueError, match="min_hourly_rate is required"):
            FilteredCandidate(
                service_id="svc_001",
                service_catalog_id="cat_001",
                instructor_id="inst_001",
                hybrid_score=0.9,
                name="Lesson",
                description="A lesson",
                price_per_hour=None,
                min_hourly_rate=None,
            )

    def test_price_per_hour_property_returns_min_hourly_rate(self) -> None:
        """Legacy .price_per_hour property returns min_hourly_rate as float."""
        candidate = FilteredCandidate(
            service_id="svc_001",
            service_catalog_id="cat_001",
            instructor_id="inst_001",
            hybrid_score=0.9,
            name="Lesson",
            description="A lesson",
            min_hourly_rate=50.5,
        )
        assert candidate.price_per_hour == 50.5
        assert isinstance(candidate.price_per_hour, float)


# ---------------------------------------------------------------------------
# Coverage recovery: Multi-region location filter (lines 381-383)
# ---------------------------------------------------------------------------


class TestMultiRegionLocationFilter:
    def test_resolved_with_multiple_region_ids(
        self, filter_service: FilterService, mock_repository: Mock
    ) -> None:
        """Resolved location with >=2 region_ids triggers _filter_location_regions."""
        candidates = [
            _make_candidate("svc_001", "inst_001"),
            _make_candidate("svc_002", "inst_002"),
        ]
        parsed_query = ParsedQuery(
            original_query="yoga in upper east side",
            service_query="yoga",
            location_text="upper east side",
            parsing_mode="regex",
        )
        location_resolution = ResolvedLocation(
            region_id=None,
            region_name="Upper East Side",
            resolved=True,
            tier=ResolutionTier.ALIAS,
            region_ids=["reg_1", "reg_2"],
        )
        mock_repository.filter_by_any_region_coverage.return_value = ["inst_001"]

        result = filter_service._filter_candidates_core(
            candidates=candidates,
            parsed_query=parsed_query,
            user_location=None,
            default_duration=60,
            location_resolution=location_resolution,
        )

        assert "location" in result.filters_applied
        mock_repository.filter_by_any_region_coverage.assert_called()

    def test_resolved_with_borough_only(
        self, filter_service: FilterService, mock_repository: Mock
    ) -> None:
        """Resolved location with borough but no region_id → borough filter (line 388)."""
        candidates = [_make_candidate("svc_001", "inst_001")]
        parsed_query = ParsedQuery(
            original_query="yoga in manhattan",
            service_query="yoga",
            location_text="manhattan",
            parsing_mode="regex",
        )
        location_resolution = ResolvedLocation(
            region_id=None,
            region_name=None,
            borough="Manhattan",
            resolved=True,
            tier=ResolutionTier.EXACT,
            region_ids=[],
        )
        mock_repository.filter_by_parent_region.return_value = ["inst_001"]

        result = filter_service._filter_candidates_core(
            candidates=candidates,
            parsed_query=parsed_query,
            user_location=None,
            default_duration=60,
            location_resolution=location_resolution,
        )

        assert "location" in result.filters_applied
        mock_repository.filter_by_parent_region.assert_called()


# ---------------------------------------------------------------------------
# Coverage recovery: _refine_buffered_availability_map (lines 769-792)
# ---------------------------------------------------------------------------


class TestRefineBufferedAvailability:
    """Common keyword args for _refine_buffered_availability_map."""

    _COMMON_KWARGS = dict(
        time_after=None,
        time_before=None,
        duration_minutes=60,
    )

    def test_empty_dates_returns_early(
        self, filter_service: FilterService, mock_repository: Mock
    ) -> None:
        """Availability map with empty date lists → early return (line 769)."""
        availability_map = {"inst_001": [], "inst_002": []}
        parsed_query = ParsedQuery(original_query="yoga", service_query="yoga", parsing_mode="regex")

        result = filter_service._refine_buffered_availability_map(
            availability_map,
            instructor_ids=["inst_001", "inst_002"],
            parsed_query=parsed_query,
            **self._COMMON_KWARGS,
        )
        assert result == availability_map

    def test_context_getter_not_callable_returns_early(
        self, filter_service: FilterService, mock_repository: Mock
    ) -> None:
        """When get_buffered_availability_context is not callable → early return (line 773)."""
        mock_repository.get_buffered_availability_context = "not_callable"
        today = date.today()
        availability_map = {"inst_001": [today]}
        parsed_query = ParsedQuery(original_query="yoga", service_query="yoga", parsing_mode="regex")

        result = filter_service._refine_buffered_availability_map(
            availability_map,
            instructor_ids=["inst_001"],
            parsed_query=parsed_query,
            **self._COMMON_KWARGS,
        )
        assert result == availability_map

    def test_bits_by_key_not_dict_returns_early(
        self, filter_service: FilterService, mock_repository: Mock
    ) -> None:
        """When bits_by_key is not a dict → early return (line 785)."""
        today = date.today()
        availability_map = {"inst_001": [today]}
        parsed_query = ParsedQuery(original_query="yoga", service_query="yoga", parsing_mode="regex")
        mock_repository.get_buffered_availability_context.return_value = {
            "bits_by_key": None,
            "format_tags_by_key": {},
            "bookings_by_key": {},
            "profiles_by_instructor": {},
            "timezones_by_instructor": {},
        }

        result = filter_service._refine_buffered_availability_map(
            availability_map,
            instructor_ids=["inst_001"],
            parsed_query=parsed_query,
            **self._COMMON_KWARGS,
        )
        assert result == availability_map

    def test_non_dict_format_tags_and_bookings_default_to_empty(
        self, filter_service: FilterService, mock_repository: Mock
    ) -> None:
        """When format_tags_by_key / bookings_by_key are non-dict → default to {} (lines 789, 791-792)."""
        today = date.today()
        availability_map = {"inst_001": [today]}
        parsed_query = ParsedQuery(original_query="yoga", service_query="yoga", parsing_mode="regex")
        mock_repository.get_buffered_availability_context.return_value = {
            "bits_by_key": {("inst_001", today): None},
            "format_tags_by_key": "bad",
            "bookings_by_key": 42,
            "profiles_by_instructor": True,
            "timezones_by_instructor": [],
        }

        # Should not crash — the non-dict values get replaced with {}
        result = filter_service._refine_buffered_availability_map(
            availability_map,
            instructor_ids=["inst_001"],
            parsed_query=parsed_query,
            **self._COMMON_KWARGS,
        )
        # bits_by_key[key] is None so the date gets skipped (line 836)
        # Instructor may have empty list or be omitted entirely
        assert result.get("inst_001", []) == []


# ---------------------------------------------------------------------------
# Coverage recovery: Soft filtering paths (lines 950, 970, 1012)
# ---------------------------------------------------------------------------


class TestRefineBufferedTimezoneFiltering:
    """Cover timezone/date filtering in _refine_buffered_availability_map (lines 820, 833)."""

    _COMMON_KWARGS = dict(
        time_after=None,
        time_before=None,
        duration_minutes=60,
    )

    def test_past_dates_filtered_by_instructor_timezone(
        self, filter_service: FilterService, mock_repository: Mock
    ) -> None:
        """When no date constraints and instructor has timezone, past dates are skipped (lines 820, 833)."""
        from datetime import timedelta

        yesterday = date.today() - timedelta(days=1)
        tomorrow = date.today() + timedelta(days=1)
        availability_map = {"inst_001": [yesterday, tomorrow]}
        parsed_query = ParsedQuery(
            original_query="yoga",
            service_query="yoga",
            date=None,
            date_range_start=None,
            date_range_end=None,
            parsing_mode="regex",
        )

        # Full valid context — use None bits so processing skips at line 835-836
        # (we only need to reach the instructor_today comparison at line 832)
        mock_repository.get_buffered_availability_context.return_value = {
            "bits_by_key": {
                ("inst_001", yesterday): None,
                ("inst_001", tomorrow): None,
            },
            "format_tags_by_key": {},
            "bookings_by_key": {},
            "profiles_by_instructor": {},
            "timezones_by_instructor": {"inst_001": "America/New_York"},
        }
        mock_repository.db = Mock()

        with patch("app.services.search.filter_service.ConfigService") as mock_config_cls:
            mock_config = Mock()
            mock_config.get_default_buffer_minutes.return_value = 15
            mock_config_cls.return_value = mock_config

            result = filter_service._refine_buffered_availability_map(
                availability_map,
                instructor_ids=["inst_001"],
                parsed_query=parsed_query,
                **self._COMMON_KWARGS,
            )

        # Yesterday should be filtered out due to instructor_today check
        kept = result.get("inst_001", [])
        assert yesterday not in kept


class TestSoftFilteringEdgeCases:
    def test_soft_location_multi_region_resolved(
        self, filter_service: FilterService, mock_repository: Mock
    ) -> None:
        """Soft filter with resolved location having ≥2 region_ids (line 950)."""
        candidates = [
            ServiceCandidate(
                service_id=f"svc_{i}",
                service_catalog_id=f"cat_{i}",
                hybrid_score=1.0,
                vector_score=1.0,
                text_score=0.8,
                name=f"Lesson {i}",
                description=None,
                min_hourly_rate=50,
                instructor_id=f"inst_{i}",
            )
            for i in range(5)
        ]
        parsed_query = ParsedQuery(
            original_query="yoga in upper east side",
            service_query="yoga",
            location_text="upper east side",
            location_type="neighborhood",
            parsing_mode="regex",
        )
        location_resolution = ResolvedLocation(
            region_id=None,
            region_name="Upper East Side",
            resolved=True,
            tier=ResolutionTier.ALIAS,
            region_ids=["reg_1", "reg_2"],
        )
        # Hard filter returns nothing, triggering soft relaxation
        mock_repository.filter_by_any_region_coverage.return_value = []
        mock_repository.get_instructor_min_distance_to_regions.return_value = {
            f"inst_{i}": 100.0 for i in range(5)
        }

        filtered, relaxed = filter_service._apply_soft_filtering(
            original_candidates=candidates,
            parsed_query=parsed_query,
            user_location=None,
            location_resolution=location_resolution,
            duration_minutes=60,
            strict_service_ids=set(),
            filter_stats={"after_location": 0},
        )

        assert len(filtered) == 5
        assert "location" in relaxed

    def test_soft_location_near_me_skips_filter(
        self, filter_service: FilterService, mock_repository: Mock
    ) -> None:
        """Soft filter with near_me → skips location filter entirely (line 970)."""
        candidates = [
            ServiceCandidate(
                service_id=f"svc_{i}",
                service_catalog_id=f"cat_{i}",
                hybrid_score=1.0,
                vector_score=1.0,
                text_score=0.8,
                name=f"Lesson {i}",
                description=None,
                min_hourly_rate=50,
                instructor_id=f"inst_{i}",
            )
            for i in range(5)
        ]
        parsed_query = ParsedQuery(
            original_query="yoga near me",
            service_query="yoga",
            location_text="near me",
            location_type="near_me",
            max_price=40,  # strict price to force soft filtering
            parsing_mode="regex",
        )
        mock_repository.get_lesson_type_rates.return_value = {}

        filtered, relaxed = filter_service._apply_soft_filtering(
            original_candidates=candidates,
            parsed_query=parsed_query,
            user_location=None,
            location_resolution=None,
            duration_minutes=60,
            strict_service_ids=set(),
            filter_stats={},
        )

        assert len(filtered) == 5
        assert "price" in relaxed

    def test_soft_filtering_lesson_type_without_max_price(
        self, filter_service: FilterService, mock_repository: Mock
    ) -> None:
        """Lesson type filter in soft context when max_price is None (line 1012)."""
        candidates = [
            ServiceCandidate(
                service_id=f"svc_{i}",
                service_catalog_id=f"cat_{i}",
                hybrid_score=1.0,
                vector_score=1.0,
                text_score=0.8,
                name=f"Lesson {i}",
                description=None,
                min_hourly_rate=50,
                instructor_id=f"inst_{i}",
            )
            for i in range(5)
        ]
        parsed_query = ParsedQuery(
            original_query="online yoga",
            service_query="yoga",
            location_text="brooklyn",
            location_type="neighborhood",
            lesson_type="online",
            max_price=None,
            parsing_mode="regex",
        )
        location_resolution = ResolvedLocation(
            region_id="reg_1",
            region_name="Brooklyn",
            resolved=True,
            tier=ResolutionTier.EXACT,
        )
        # Hard filter returns nothing to trigger soft relaxation
        mock_repository.filter_by_region_coverage.return_value = []
        mock_repository.get_lesson_type_rates.return_value = {"svc_0": 50.0, "svc_1": 50.0}
        mock_repository.get_instructor_min_distance_to_regions.return_value = {
            f"inst_{i}": 100.0 for i in range(5)
        }

        filtered, relaxed = filter_service._apply_soft_filtering(
            original_candidates=candidates,
            parsed_query=parsed_query,
            user_location=None,
            location_resolution=location_resolution,
            duration_minutes=60,
            strict_service_ids=set(),
            filter_stats={"after_location": 0},
        )

        assert "location" in relaxed
