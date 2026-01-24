from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
import pytest

from app.models.instructor import InstructorProfile
from app.models.nl_search import SearchClick, SearchQuery
from app.models.service_catalog import ServiceCatalog


def _clear_search_data(db) -> None:
    db.query(SearchClick).delete()
    db.query(SearchQuery).delete()
    db.commit()


def _create_search_query(
    db,
    *,
    query: str,
    result_count: int,
    created_at: datetime,
) -> SearchQuery:
    row = SearchQuery(
        original_query=query,
        normalized_query={"q": query},
        parsing_mode="regex",
        parsing_latency_ms=5,
        result_count=result_count,
        total_latency_ms=12,
        created_at=created_at,
    )
    db.add(row)
    db.flush()
    return row


def _create_book_click(db, *, search_query: SearchQuery, instructor_profile_id: str) -> None:
    service = db.query(ServiceCatalog).first()
    assert service is not None
    click = SearchClick(
        search_query_id=search_query.id,
        service_id=service.id,
        instructor_id=instructor_profile_id,
        position=1,
        action="book",
    )
    db.add(click)


def test_top_queries_structure_and_filters(
    client: TestClient,
    db,
    test_instructor,
    auth_headers_admin,
):
    _clear_search_data(db)
    base_time = datetime(2030, 1, 15, tzinfo=timezone.utc)
    profile = (
        db.query(InstructorProfile)
        .filter(InstructorProfile.user_id == test_instructor.id)
        .first()
    )
    assert profile is not None

    q1 = _create_search_query(
        db,
        query="piano lessons",
        result_count=10,
        created_at=base_time - timedelta(days=1),
    )
    _create_search_query(
        db,
        query="piano lessons",
        result_count=6,
        created_at=base_time - timedelta(days=2),
    )
    _create_search_query(
        db,
        query="guitar teacher nyc",
        result_count=4,
        created_at=base_time - timedelta(days=1),
    )
    _create_search_query(
        db,
        query="piano lessons",
        result_count=3,
        created_at=base_time - timedelta(days=45),
    )
    _create_book_click(db, search_query=q1, instructor_profile_id=profile.id)
    db.commit()

    start_date = (base_time - timedelta(days=7)).date()
    end_date = base_time.date()

    res = client.get(
        "/api/v1/admin/mcp/search/top-queries",
        headers=auth_headers_admin,
        params={"start_date": start_date, "end_date": end_date},
    )
    assert res.status_code == 200
    payload = res.json()
    assert "meta" in payload
    data = payload["data"]
    assert data["total_searches"] == 3
    assert data["time_window"]["start"] == start_date.isoformat()
    assert data["time_window"]["end"] == end_date.isoformat()

    assert len(data["queries"]) == 1
    top = data["queries"][0]
    assert top["query"] == "piano lessons"
    assert top["count"] == 2
    assert top["conversion_rate"] == pytest.approx(0.5)
    assert top["avg_results"] == pytest.approx(8.0)

    res = client.get(
        "/api/v1/admin/mcp/search/top-queries",
        headers=auth_headers_admin,
        params={"start_date": start_date, "end_date": end_date, "min_count": 1, "limit": 1},
    )
    assert res.status_code == 200
    assert len(res.json()["data"]["queries"]) == 1


def test_zero_results_rate(
    client: TestClient,
    db,
    auth_headers_admin,
):
    _clear_search_data(db)
    base_time = datetime(2030, 1, 15, tzinfo=timezone.utc)
    _create_search_query(
        db,
        query="kubernetes training",
        result_count=0,
        created_at=base_time - timedelta(days=1),
    )
    _create_search_query(
        db,
        query="kubernetes training",
        result_count=0,
        created_at=base_time - timedelta(days=2),
    )
    _create_search_query(
        db,
        query="piano lessons",
        result_count=5,
        created_at=base_time - timedelta(days=1),
    )
    db.commit()

    start_date = (base_time - timedelta(days=7)).date()
    end_date = base_time.date()

    res = client.get(
        "/api/v1/admin/mcp/search/zero-results",
        headers=auth_headers_admin,
        params={"start_date": start_date, "end_date": end_date},
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["total_zero_result_searches"] == 2
    assert data["zero_result_rate"] == pytest.approx(0.6667, rel=1e-4)
    assert data["queries"][0]["query"] == "kubernetes training"
    assert data["queries"][0]["count"] == 2


def test_search_permissions(client: TestClient, auth_headers):
    res = client.get("/api/v1/admin/mcp/search/top-queries", headers=auth_headers)
    assert res.status_code == 403

    res = client.get("/api/v1/admin/mcp/search/zero-results", headers=auth_headers)
    assert res.status_code == 403
