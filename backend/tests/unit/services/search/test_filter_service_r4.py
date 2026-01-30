from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

import app.services.search.filter_service as filter_service_module
from app.services.search.filter_service import (
    MIN_RESULTS_BEFORE_SOFT_FILTER,
    FilterService,
)
from app.services.search.location_resolver import ResolvedLocation
from app.services.search.query_parser import ParsedQuery
from app.services.search.retriever import ServiceCandidate


def _candidate(idx: int, price: int = 50) -> ServiceCandidate:
    return ServiceCandidate(
        service_id=f"svc_{idx}",
        service_catalog_id=f"cat_{idx}",
        hybrid_score=0.5,
        vector_score=0.5,
        text_score=0.5,
        name=f"Service {idx}",
        description=None,
        price_per_hour=price,
        instructor_id=f"inst_{idx}",
    )


def _base_query(**overrides) -> ParsedQuery:
    return ParsedQuery(
        original_query="piano lessons",
        service_query="piano lessons",
        parsing_mode="regex",
        **overrides,
    )


@pytest.fixture
def repository() -> Mock:
    repo = Mock()
    repo.filter_by_location.return_value = ["inst_1", "inst_2", "inst_3"]
    repo.filter_by_location_soft.return_value = ["inst_1", "inst_2", "inst_3"]
    repo.filter_by_region_coverage.return_value = []
    repo.filter_by_any_region_coverage.return_value = []
    repo.filter_by_parent_region.return_value = ["inst_1", "inst_2"]
    repo.get_instructor_min_distance_to_regions.return_value = {"inst_1": 5000, "inst_2": 9000}
    today = date.today()
    repo.filter_by_availability.return_value = {
        "inst_1": [today],
        "inst_2": [today + timedelta(days=1)],
    }
    repo.check_weekend_availability.return_value = {
        "inst_1": [today],
        "inst_2": [today],
    }
    repo.filter_by_lesson_type.return_value = ["svc_1"]
    return repo


@pytest.mark.asyncio
async def test_filter_candidates_resolves_location_with_overrides(repository: Mock) -> None:
    resolver = Mock()
    resolver.region_code = "nyc"
    resolver.resolve = AsyncMock(return_value=ResolvedLocation.from_not_found())

    service = FilterService(repository=repository, location_resolver=resolver, region_code="nyc")

    candidates = [_candidate(1)]
    query = _base_query(location_text="brooklyn", location_type="neighborhood")

    result = await service.filter_candidates(candidates, query)

    assert result.total_before_filter == 1
    resolver.resolve.assert_called_once()


def test_filter_candidates_sync_requires_overrides() -> None:
    service = FilterService()

    with pytest.raises(RuntimeError):
        service.filter_candidates_sync([], _base_query())


def test_filter_candidates_sync_resolves_location_with_overrides(repository: Mock) -> None:
    resolver = Mock()
    resolver.region_code = "nyc"
    resolver.resolve_sync.return_value = ResolvedLocation.from_not_found()

    service = FilterService(repository=repository, location_resolver=resolver, region_code="nyc")

    candidates = [_candidate(1)]
    query = _base_query(location_text="queens", location_type="neighborhood")

    service.filter_candidates_sync(candidates, query)

    resolver.resolve_sync.assert_called_once()


def test_filter_candidates_lesson_type_applied(repository: Mock) -> None:
    resolver = Mock()
    resolver.region_code = "nyc"
    service = FilterService(repository=repository, location_resolver=resolver, region_code="nyc")

    candidates = [_candidate(1), _candidate(2)]
    query = _base_query(lesson_type="online")

    result = service._filter_candidates_core(
        candidates,
        query,
        user_location=None,
        default_duration=60,
        location_resolution=None,
    )

    assert result.filters_applied == ["lesson_type"]
    assert result.filter_stats["after_lesson_type"] == 1


def test_location_resolution_defaults_to_not_found(repository: Mock) -> None:
    resolver = Mock()
    resolver.region_code = "nyc"
    service = FilterService(repository=repository, location_resolver=resolver, region_code="nyc")

    candidates = [_candidate(1)]
    query = _base_query(location_text="unknown", location_type="neighborhood")

    result = service._filter_candidates_core(
        candidates,
        query,
        user_location=None,
        default_duration=60,
        location_resolution=None,
    )

    assert result.location_resolution is not None
    assert result.location_resolution.not_found is True


def test_perf_logging_path_emits(repository: Mock, monkeypatch) -> None:
    resolver = Mock()
    resolver.region_code = "nyc"
    service = FilterService(repository=repository, location_resolver=resolver, region_code="nyc")

    monkeypatch.setattr(filter_service_module, "_PERF_LOG_ENABLED", True)
    monkeypatch.setattr(filter_service_module, "_PERF_LOG_SLOW_MS", 0)

    logger = Mock()
    monkeypatch.setattr(filter_service_module, "logger", logger)

    candidates = [_candidate(1)]
    query = _base_query()

    service._filter_candidates_core(
        candidates,
        query,
        user_location=None,
        default_duration=60,
        location_resolution=None,
    )

    assert logger.info.called


def test_filter_location_empty_candidates(repository: Mock) -> None:
    service = FilterService(repository=repository, location_resolver=Mock(), region_code="nyc")
    assert service._filter_location([], (0.0, 0.0)) == []


def test_filter_location_marks_failed(repository: Mock) -> None:
    repository.filter_by_location.return_value = []
    service = FilterService(repository=repository, location_resolver=Mock(), region_code="nyc")

    candidates = [
        filter_service_module.FilteredCandidate(
            service_id="svc_1",
            service_catalog_id="cat_1",
            instructor_id="inst_1",
            hybrid_score=0.5,
            name="Service",
            description=None,
            price_per_hour=50,
        )
    ]

    result = service._filter_location(candidates, (0.0, 0.0))
    assert result == []
    assert candidates[0].passed_location is False


def test_filter_location_region_empty_candidates(repository: Mock) -> None:
    service = FilterService(repository=repository, location_resolver=Mock(), region_code="nyc")
    assert service._filter_location_region([], "region-1") == []


def test_filter_location_regions_no_ids_returns_candidates(repository: Mock) -> None:
    service = FilterService(repository=repository, location_resolver=Mock(), region_code="nyc")
    candidates = [
        filter_service_module.FilteredCandidate(
            service_id="svc_1",
            service_catalog_id="cat_1",
            instructor_id="inst_1",
            hybrid_score=0.5,
            name="Service",
            description=None,
            price_per_hour=50,
        )
    ]

    result = service._filter_location_regions(candidates, [])
    assert result == candidates


def test_filter_availability_empty_candidates(repository: Mock) -> None:
    service = FilterService(repository=repository, location_resolver=Mock(), region_code="nyc")
    assert service._filter_availability([], _base_query(), 60) == []


def test_filter_availability_weekend_without_range_uses_next_week(repository: Mock) -> None:
    service = FilterService(repository=repository, location_resolver=Mock(), region_code="nyc")
    repository.filter_by_availability.return_value = {"inst_1": [date.today()]}

    candidates = [
        filter_service_module.FilteredCandidate(
            service_id="svc_1",
            service_catalog_id="cat_1",
            instructor_id="inst_1",
            hybrid_score=0.5,
            name="Service",
            description=None,
            price_per_hour=50,
        )
    ]

    query = _base_query(date_type="weekend")

    service._filter_availability(candidates, query, 60)

    repository.filter_by_availability.assert_called_once()


def test_apply_soft_filtering_returns_early_with_enough_results(repository: Mock) -> None:
    resolver = Mock()
    resolver.region_code = "nyc"
    service = FilterService(repository=repository, location_resolver=resolver, region_code="nyc")

    candidates = [_candidate(i) for i in range(MIN_RESULTS_BEFORE_SOFT_FILTER)]
    query = _base_query(location_text="manhattan", location_type="neighborhood")
    location_resolution = ResolvedLocation(resolved=True)

    filtered, relaxed = service._apply_soft_filtering(
        original_candidates=candidates,
        parsed_query=query,
        user_location=None,
        location_resolution=location_resolution,
        duration_minutes=60,
        strict_service_ids=set(),
        filter_stats={"after_location": 0},
    )

    assert len(filtered) == MIN_RESULTS_BEFORE_SOFT_FILTER
    assert relaxed == []


def test_apply_soft_filtering_time_relax_returns_early(repository: Mock) -> None:
    resolver = Mock()
    resolver.region_code = "nyc"
    service = FilterService(repository=repository, location_resolver=resolver, region_code="nyc")

    candidates = [_candidate(i) for i in range(6)]

    def availability_side_effect(instructor_ids, target_date, time_after, time_before, duration_minutes):
        if time_after:
            return {"inst_0": [date.today()], "inst_1": [date.today()]}
        return {iid: [date.today()] for iid in instructor_ids}

    repository.filter_by_availability.side_effect = availability_side_effect

    query = _base_query(time_after="09:00", time_before="10:00")

    filtered, relaxed = service._apply_soft_filtering(
        original_candidates=candidates,
        parsed_query=query,
        user_location=None,
        location_resolution=None,
        duration_minutes=60,
        strict_service_ids=set(),
        filter_stats={"after_location": 0},
    )

    assert len(filtered) >= MIN_RESULTS_BEFORE_SOFT_FILTER
    assert "time" in relaxed


def test_apply_soft_filtering_effective_constraints(repository: Mock) -> None:
    resolver = Mock()
    resolver.region_code = "nyc"
    service = FilterService(repository=repository, location_resolver=resolver, region_code="nyc")

    candidates = [_candidate(i) for i in range(3)]

    def availability_side_effect(instructor_ids, target_date, time_after, time_before, duration_minutes):
        # Tight constraints -> fewer instructors
        if time_after or target_date:
            return {"inst_0": [date.today()]}
        return {iid: [date.today()] for iid in instructor_ids[:2]}

    repository.filter_by_availability.side_effect = availability_side_effect
    repository.filter_by_region_coverage.return_value = []
    repository.get_instructor_min_distance_to_regions.return_value = {"inst_0": 5000, "inst_1": 6000}

    query = _base_query(
        time_after="09:00",
        date=date.today(),
        location_text="upper east side",
        location_type="neighborhood",
    )
    location_resolution = ResolvedLocation(resolved=True, region_id="region-1")

    filtered, relaxed = service._apply_soft_filtering(
        original_candidates=candidates,
        parsed_query=query,
        user_location=None,
        location_resolution=location_resolution,
        duration_minutes=60,
        strict_service_ids=set(),
        filter_stats={"after_location": 0},
    )

    assert "time" in relaxed
    assert "date" in relaxed
    assert "location" in relaxed
    assert filtered


def test_apply_soft_filtering_location_soft_user_location(repository: Mock) -> None:
    resolver = Mock()
    resolver.region_code = "nyc"
    service = FilterService(repository=repository, location_resolver=resolver, region_code="nyc")

    candidates = [_candidate(i) for i in range(3)]
    repository.filter_by_location_soft.return_value = ["inst_0", "inst_1"]

    query = _base_query()

    filtered, relaxed = service._apply_soft_filtering(
        original_candidates=candidates,
        parsed_query=query,
        user_location=(-73.9, 40.7),
        location_resolution=None,
        duration_minutes=60,
        strict_service_ids=set(),
        filter_stats={"after_location": 0},
    )

    assert filtered
    assert "location" in relaxed or relaxed == []


def test_apply_soft_filtering_location_soft_requires_clarification(repository: Mock) -> None:
    resolver = Mock()
    resolver.region_code = "nyc"
    service = FilterService(repository=repository, location_resolver=resolver, region_code="nyc")

    candidates = [_candidate(i) for i in range(2)]
    repository.get_instructor_min_distance_to_regions.return_value = {"inst_0": 5000}

    query = _base_query(location_text="ues", location_type="neighborhood")
    location_resolution = ResolvedLocation(
        requires_clarification=True,
        candidates=[{"region_id": "r1"}, {"region_id": "r1"}, {"region_id": "r2"}],
    )

    filtered, relaxed = service._apply_soft_filtering(
        original_candidates=candidates,
        parsed_query=query,
        user_location=None,
        location_resolution=location_resolution,
        duration_minutes=60,
        strict_service_ids=set(),
        filter_stats={"after_location": 0},
    )

    assert filtered
    assert "location" in relaxed or relaxed == []


def test_apply_soft_filtering_location_soft_unresolved_returns_candidates(repository: Mock) -> None:
    resolver = Mock()
    resolver.region_code = "nyc"
    service = FilterService(repository=repository, location_resolver=resolver, region_code="nyc")

    candidates = [_candidate(i) for i in range(2)]
    query = _base_query(location_text="somewhere", location_type="neighborhood")
    location_resolution = ResolvedLocation()

    filtered, relaxed = service._apply_soft_filtering(
        original_candidates=candidates,
        parsed_query=query,
        user_location=None,
        location_resolution=location_resolution,
        duration_minutes=60,
        strict_service_ids=set(),
        filter_stats={"after_location": 0},
    )

    assert filtered
    assert relaxed is not None


def test_apply_soft_filtering_location_soft_borough_only_returns_candidates(repository: Mock) -> None:
    resolver = Mock()
    resolver.region_code = "nyc"
    service = FilterService(repository=repository, location_resolver=resolver, region_code="nyc")

    candidates = [_candidate(i) for i in range(2)]
    query = _base_query(location_text="brooklyn", location_type="borough")
    location_resolution = ResolvedLocation(resolved=True, borough="Brooklyn")

    filtered, relaxed = service._apply_soft_filtering(
        original_candidates=candidates,
        parsed_query=query,
        user_location=None,
        location_resolution=location_resolution,
        duration_minutes=60,
        strict_service_ids=set(),
        filter_stats={"after_location": 0},
    )

    assert filtered
    assert relaxed is not None
