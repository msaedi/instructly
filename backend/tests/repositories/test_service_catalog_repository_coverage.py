from datetime import datetime, timedelta, timezone

import pytest

from app.models.service_catalog import InstructorService, ServiceAnalytics, ServiceCatalog
import app.repositories.service_catalog_repository as _scr_module
from app.repositories.service_catalog_repository import (
    ServiceAnalyticsRepository,
    ServiceCatalogRepository,
    _apply_active_catalog_predicate,
    _apply_instructor_service_active_filter,
)


def _vector(size, value=0.01):
    return [value] * size


def test_find_similar_by_embedding_success(db, sample_catalog_services):
    service = sample_catalog_services[0]
    embedding = _vector(384, 0.02)
    service.embedding = embedding
    db.commit()

    repo = ServiceCatalogRepository(db)
    results = repo.find_similar_by_embedding(embedding, limit=5, threshold=0.0)

    assert results
    assert results[0][0].id == service.id


def test_service_catalog_repository_pg_trgm_init_failure(db, monkeypatch):
    def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    # Reset module-level cache so the check actually runs
    monkeypatch.setattr(_scr_module, "_pg_trgm_available", None)
    monkeypatch.setattr(db, "execute", _boom)
    repo = ServiceCatalogRepository(db)
    assert repo._pg_trgm_available is False


def test_find_similar_by_embedding_no_results(db, monkeypatch):
    class _EmptyResult:
        def fetchall(self):
            return []

    repo = ServiceCatalogRepository(db)
    monkeypatch.setattr(repo.db, "execute", lambda *_a, **_k: _EmptyResult())
    assert repo.find_similar_by_embedding(_vector(384)) == []


def test_find_similar_by_embedding_error_returns_empty(db, monkeypatch):
    repo = ServiceCatalogRepository(db)

    def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(repo.db, "execute", _boom)
    assert repo.find_similar_by_embedding(_vector(384)) == []


def test_search_services_trgm_and_fallback(db, sample_catalog_services):
    repo = ServiceCatalogRepository(db)
    repo._pg_trgm_available = False

    fallback_results = repo.search_services(query_text="piano", limit=5)
    assert isinstance(fallback_results, list)

    repo._pg_trgm_available = True
    try:
        trigram_results = repo.search_services(query_text="piano", limit=5)
        assert isinstance(trigram_results, list)
    except Exception as exc:
        pytest.skip(f"pg_trgm not available: {exc}")


def test_active_predicate_helpers(db):
    query = _apply_active_catalog_predicate(db.query(ServiceCatalog))
    assert query is not None

    service_query = _apply_instructor_service_active_filter(db.query(InstructorService))
    assert service_query is not None


def test_popular_and_trending_services(db, sample_catalog_services):
    service = sample_catalog_services[0]
    analytics_repo = ServiceAnalyticsRepository(db)
    analytics_repo.get_or_create(service.id)
    analytics_repo.update(
        service.id,
        booking_count_7d=5,
        booking_count_30d=10,
        search_count_7d=70,
        search_count_30d=30,
        view_to_booking_rate=0.2,
        last_calculated=datetime.now(timezone.utc),
    )

    repo = ServiceCatalogRepository(db)

    popular_7d = repo.get_popular_services(limit=5, days=7)
    popular_30d = repo.get_popular_services(limit=5, days=30)
    trending = repo.get_trending_services(limit=5)

    assert popular_7d
    assert popular_30d
    assert any(item["service"].id == service.id for item in popular_7d)
    assert any(s.id == service.id for s in trending)


def test_update_display_order_by_popularity(db, sample_catalog_services):
    analytics_repo = ServiceAnalyticsRepository(db)
    for idx, service in enumerate(sample_catalog_services, start=1):
        analytics_repo.get_or_create(service.id)
        analytics_repo.update(
            service.id,
            booking_count_30d=idx * 2,
            search_count_30d=idx,
            last_calculated=datetime.now(timezone.utc),
        )

    repo = ServiceCatalogRepository(db)
    updated = repo.update_display_order_by_popularity()
    assert updated > 0


def test_update_display_order_by_popularity_empty(db, sample_catalog_services):
    db.query(ServiceAnalytics).delete()
    db.commit()

    repo = ServiceCatalogRepository(db)
    assert repo.update_display_order_by_popularity() == 0


def test_active_services_with_categories_and_counts(db, test_instructor):
    repo = ServiceCatalogRepository(db)

    services = repo.get_active_services_with_categories(limit=5)
    assert services

    service = services[0]
    db.add(
        InstructorService(
            instructor_profile_id=test_instructor.instructor_profile.id,
            service_catalog_id=service.id,
            hourly_rate=50.0,
        )
    )
    db.commit()

    count = repo.count_active_instructors(service.id)
    assert count >= 0

    bulk = repo.count_active_instructors_bulk([service.id])
    assert service.id in bulk

    empty_bulk = repo.count_active_instructors_bulk([])
    assert empty_bulk == {}


def test_embedding_and_counts(db, sample_catalog_services):
    repo = ServiceCatalogRepository(db)

    missing = repo.get_services_needing_embedding(current_model="model_x", limit=10)
    assert isinstance(missing, list)

    assert repo.count_active_services() >= 0
    assert repo.count_services_missing_embedding() >= 0
    assert isinstance(repo.get_all_services_missing_embedding(), list)


def test_update_service_embedding_success_and_failure(db, sample_catalog_services, monkeypatch):
    service = sample_catalog_services[0]
    repo = ServiceCatalogRepository(db)

    updated = repo.update_service_embedding(
        service_id=service.id,
        embedding=_vector(1536, 0.03),
        model_name="model_test",
        text_hash="hash",
    )
    assert updated is True

    missing = repo.update_service_embedding(
        service_id="missing",
        embedding=_vector(1536, 0.01),
        model_name="model_test",
        text_hash="hash",
    )
    assert missing is False

    def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(repo.db, "query", _boom)
    assert (
        repo.update_service_embedding(
            service_id=service.id,
            embedding=_vector(1536, 0.04),
            model_name="model_test",
            text_hash="hash",
        )
        is False
    )


def test_services_available_for_kids_minimal(db, test_instructor, monkeypatch):
    repo = ServiceCatalogRepository(db)

    service = (
        db.query(InstructorService)
        .filter(InstructorService.instructor_profile_id == test_instructor.instructor_profile.id)
        .first()
    )
    assert service is not None
    service.age_groups = ["kids"]
    db.commit()

    kids_services = repo.get_services_available_for_kids_minimal()
    assert kids_services

    monkeypatch.setattr("app.repositories.base_repository.get_dialect_name", lambda _db: "sqlite")
    kids_services_fallback = repo.get_services_available_for_kids_minimal()
    assert isinstance(kids_services_fallback, list)


def test_services_available_for_kids_handles_error(db, monkeypatch):
    repo = ServiceCatalogRepository(db)

    def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(repo.db, "query", _boom)
    assert repo.get_services_available_for_kids_minimal() == []


def test_service_analytics_repository_flows(db, sample_catalog_services):
    analytics_repo = ServiceAnalyticsRepository(db)
    service = sample_catalog_services[0]

    analytics = analytics_repo.get_or_create(service.id)
    assert analytics.service_catalog_id == service.id

    by_id = analytics_repo.get_by_id(service.id)
    assert by_id is not None

    updated = analytics_repo.update(service.id, booking_count_7d=2)
    assert updated is not None

    analytics_repo.increment_search_count(service.id)

    stale_time = datetime.now(timezone.utc) - timedelta(hours=48)
    analytics.last_calculated = stale_time
    db.commit()

    stale = analytics_repo.get_stale_analytics(hours=24)
    assert stale

    analytics_repo.update_from_bookings(
        service.id,
        {
            "count_7d": 1,
            "count_30d": 2,
            "avg_price": 50.0,
            "completion_rate": 0.9,
        },
    )

    all_ids = [s.id for s in sample_catalog_services]
    missing_ids = analytics_repo.get_services_needing_analytics()
    assert isinstance(missing_ids, list)

    all_records = analytics_repo.get_all(limit=5)
    assert isinstance(all_records, list)

    bulk = analytics_repo.get_or_create_bulk(all_ids)
    assert set(bulk.keys()) >= set(all_ids)

    assert analytics_repo.get_or_create_bulk([]) == {}


def test_service_analytics_bulk_update(db, sample_catalog_services):
    analytics_repo = ServiceAnalyticsRepository(db)
    service = sample_catalog_services[0]
    analytics_repo.get_or_create(service.id)

    updates = [
        {
            "service_catalog_id": service.id,
            "booking_count_7d": 3,
            "booking_count_30d": 4,
            "active_instructors": 1,
            "total_weekly_hours": 10.0,
            "avg_price_booked": 50.0,
            "price_p25": 40.0,
            "price_p50": 50.0,
            "price_p75": 60.0,
            "most_booked_duration": 60,
            "completion_rate": 0.95,
            "supply_demand_ratio": 1.2,
            "last_calculated": datetime.now(timezone.utc),
        }
    ]

    updated = analytics_repo.bulk_update_all(updates)
    assert updated == 1
