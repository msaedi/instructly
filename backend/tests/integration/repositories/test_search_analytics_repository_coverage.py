from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from ulid import ULID

from app.models.search_event import SearchEvent, SearchEventCandidate
from app.models.search_history import SearchHistory
from app.models.service_catalog import InstructorService
from app.repositories.search_analytics_repository import SearchAnalyticsRepository


def _seed_search_events(
    db,
    user_id: str,
    service_catalog_id: str,
    *,
    guest_session_id: str | None = None,
) -> tuple[SearchEvent, SearchEvent]:
    now = datetime.now(timezone.utc)
    guest_session_id = guest_session_id or f"guest-{ULID()}"
    event_one = SearchEvent(
        user_id=user_id,
        search_query="guitar lessons",
        search_type="natural_language",
        results_count=5,
        searched_at=now - timedelta(days=1),
        session_id="sess-1",
        referrer="/home",
    )
    event_two = SearchEvent(
        guest_session_id=guest_session_id,
        search_query="piano",
        search_type="natural_language",
        results_count=0,
        searched_at=now,
        session_id="sess-2",
        referrer="/search",
    )
    db.add_all([event_one, event_two])
    db.flush()

    candidate = SearchEventCandidate(
        search_event_id=event_one.id,
        position=1,
        service_catalog_id=service_catalog_id,
        score=0.8,
        vector_score=0.7,
        lexical_score=0.6,
        source="hybrid",
        created_at=now,
    )
    db.add(candidate)
    db.flush()
    return event_one, event_two


def _seed_search_history(
    db,
    user_id: str,
    *,
    guest_session_id: str | None = None,
    converted_guest_session_id: str | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    guest_session_id = guest_session_id or f"guest-{ULID()}"
    converted_guest_session_id = converted_guest_session_id or f"guest-{ULID()}"
    guest_history = SearchHistory(
        search_query="piano",
        normalized_query="piano",
        search_type="natural_language",
        results_count=0,
        search_count=3,
        first_searched_at=now - timedelta(days=2),
        last_searched_at=now - timedelta(days=1),
        guest_session_id=guest_session_id,
        deleted_at=now - timedelta(days=1),
    )
    converted_history = SearchHistory(
        search_query="guitar",
        normalized_query="guitar",
        search_type="natural_language",
        results_count=5,
        search_count=1,
        first_searched_at=now - timedelta(days=2),
        last_searched_at=now - timedelta(days=1),
        guest_session_id=converted_guest_session_id,
        converted_to_user_id=user_id,
        converted_at=now - timedelta(days=1),
    )
    db.add_all([guest_history, converted_history])
    db.flush()


def test_search_analytics_aggregations(db, test_student, test_instructor):
    repo = SearchAnalyticsRepository(db)
    service = (
        db.query(InstructorService)
        .filter(InstructorService.instructor_profile_id == test_instructor.instructor_profile.id)
        .first()
    )
    _seed_search_events(db, test_student.id, service.service_catalog_id)
    _seed_search_history(db, test_student.id)
    db.commit()

    start = date.today() - timedelta(days=7)
    end = date.today()

    assert repo.get_search_trends(start, end)
    assert repo.get_popular_searches(start, end)
    assert repo.get_search_referrers(start, end)
    totals = repo.get_search_totals(start, end)
    assert totals.total_searches >= 1
    assert repo.get_search_type_breakdown(start, end)
    assert repo.count_zero_result_searches(start, end) >= 1
    assert repo.get_most_effective_search_type(start, end)
    assert repo.count_searches_with_results(start, end) >= 1
    assert repo.get_search_effectiveness(start, end).total_searches >= 1
    assert repo.count_searches_in_result_range(start, end, 1, 10) >= 1
    assert repo.count_searches_in_result_range(start, end, 1) >= 1

    assert repo.count_deleted_searches(start, end) >= 1
    assert repo.count_guest_sessions(start, end) >= 1
    assert repo.count_converted_guests(start, end) >= 1
    assert repo.count_engaged_guest_sessions(start, end) >= 1
    assert repo.get_avg_searches_per_guest(start, end) >= 1


def test_candidate_analytics(db, test_instructor, test_student):
    repo = SearchAnalyticsRepository(db)
    service = (
        db.query(InstructorService)
        .filter(InstructorService.instructor_profile_id == test_instructor.instructor_profile.id)
        .first()
    )
    event_one, _ = _seed_search_events(db, test_student.id, service.service_catalog_id)
    db.commit()

    start_dt = datetime.now(timezone.utc) - timedelta(days=2)
    end_dt = datetime.now(timezone.utc) + timedelta(days=1)

    summary = repo.get_candidate_summary(start_dt, end_dt)
    assert summary.total_candidates >= 1

    trends = repo.get_candidate_category_trends(start_dt, end_dt)
    assert trends

    top = repo.get_candidate_top_services(start_dt, end_dt)
    assert top

    counts = repo.get_service_instructor_counts([service.service_catalog_id])
    assert counts[service.service_catalog_id] >= 1

    assert repo.count_candidates_by_score_range(start_dt, end_dt, 0.5, 1.0) >= 1
    assert repo.count_candidates_below_score(start_dt, end_dt, 1.0) >= 1

    service_queries = repo.get_candidate_service_queries(
        service.service_catalog_id, start_dt, end_dt
    )
    assert service_queries


def test_nl_search_query_logging(db, test_instructor, test_student):
    repo = SearchAnalyticsRepository(db)
    service = (
        db.query(InstructorService)
        .filter(InstructorService.instructor_profile_id == test_instructor.instructor_profile.id)
        .first()
    )

    query_id = repo.nl_log_search_query(
        original_query="guitar",
        normalized_query={"service": "guitar"},
        parsing_mode="regex",
        parsing_latency_ms=12,
        result_count=3,
        top_result_ids=[service.id],
        total_latency_ms=45,
        cache_hit=False,
        degraded=False,
        user_id=test_student.id,
        session_id="sess-nl",
    )
    service_catalog_id, instructor_profile_id = repo.nl_resolve_click_targets(
        service_id=service.id,
        instructor_id=test_instructor.id,
    )
    click_id = repo.nl_log_search_click(
        search_query_id=query_id,
        service_id=service_catalog_id,
        instructor_id=instructor_profile_id,
        position=1,
        action="view",
    )
    assert click_id

    popular = repo.nl_get_popular_queries(days=7)
    assert popular

    zero = repo.nl_get_zero_result_queries(days=7)
    assert isinstance(zero, list)

    metrics = repo.nl_get_search_metrics(days=7)
    assert metrics["total_searches"] >= 1
