from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import AsyncMock

from app.api.dependencies.services import get_cache_service_dep
from app.core.ulid_helper import generate_ulid
from app.main import fastapi_app as app
from app.models.address import UserAddress
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService
from app.repositories.search_analytics_repository import SearchAnalyticsRepository
from app.schemas.nl_search import NLSearchMeta, NLSearchResponse, ParsedQueryInfo
from app.services.search.nl_search_service import NLSearchService


class FakeCacheService:
    def __init__(self, cached: dict | None = None) -> None:
        self._cached = cached or {}
        self.set_calls: list[tuple[str, dict, int | None]] = []

    async def get_json(self, key: str):
        return self._cached.get(key)

    async def set_json(self, key: str, value: dict, ttl: int | None = None) -> bool:
        self._cached[key] = value
        self.set_calls.append((key, value, ttl))
        return True

    async def get(self, key: str):
        return self._cached.get(key)


def _make_search_response(query: str, *, cache_hit: bool = False) -> NLSearchResponse:
    parsed = ParsedQueryInfo(service_query=query)
    meta = NLSearchMeta(
        query=query,
        parsed=parsed,
        total_results=0,
        limit=20,
        latency_ms=5,
        cache_hit=cache_hit,
        degraded=False,
        parsing_mode="regex",
    )
    return NLSearchResponse(results=[], meta=meta)


@contextmanager
def _override_cache_service(fake_cache: FakeCacheService):
    previous_override = app.dependency_overrides.get(get_cache_service_dep)
    app.dependency_overrides[get_cache_service_dep] = lambda: fake_cache
    try:
        yield
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_cache_service_dep, None)
        else:
            app.dependency_overrides[get_cache_service_dep] = previous_override


def test_search_rejects_blank_query(client) -> None:
    response = client.get("/api/v1/search", params={"q": "   "})
    assert response.status_code == 400


def test_search_requires_lat_lng_pair(client) -> None:
    response = client.get("/api/v1/search", params={"q": "piano", "lat": 40.7})
    assert response.status_code == 400

    response = client.get("/api/v1/search", params={"q": "piano", "lng": -73.9})
    assert response.status_code == 400


def test_search_near_me_requires_auth(client, monkeypatch) -> None:
    async def fake_search(self, query: str, **kwargs) -> NLSearchResponse:
        return _make_search_response(query)

    monkeypatch.setattr(NLSearchService, "search", fake_search)

    fake_cache = FakeCacheService()
    with _override_cache_service(fake_cache):
        response = client.get("/api/v1/search", params={"q": "near me"})

    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["requires_auth"] is True
    assert "sign in" in (data["meta"]["location_message"] or "").lower()


def test_search_near_me_uses_default_address(
    client,
    db,
    test_student,
    auth_headers_student,
    monkeypatch,
) -> None:
    address = UserAddress(
        user_id=test_student.id,
        street_line1="123 Main St",
        locality="New York",
        administrative_area="NY",
        postal_code="10001",
        country_code="US",
        latitude=40.7527,
        longitude=-73.9772,
        is_default=True,
        is_active=True,
    )
    db.add(address)
    db.commit()

    captured = {}

    async def fake_search(self, query: str, user_location=None, **kwargs) -> NLSearchResponse:
        captured["user_location"] = user_location
        return _make_search_response(query)

    monkeypatch.setattr(NLSearchService, "search", fake_search)
    monkeypatch.setattr(
        "app.routes.v1.search.RegionBoundaryRepository.find_region_by_point",
        lambda *args, **kwargs: {"region_name": "Manhattan - Midtown"},
    )

    fake_cache = FakeCacheService()
    with _override_cache_service(fake_cache):
        response = client.get("/api/v1/search", params={"q": "near me"}, headers=auth_headers_student)

    assert response.status_code == 200
    data = response.json()
    assert captured["user_location"] == (-73.9772, 40.7527)
    assert data["meta"]["requires_address"] is False
    assert data["meta"]["location_resolved"] == "Manhattan - Midtown"
    assert data["meta"]["parsed"]["location"] == "near me"
    assert fake_cache.set_calls


def test_search_admin_flags_require_admin(client, monkeypatch) -> None:
    async def fake_search(self, query: str, **kwargs) -> NLSearchResponse:
        return _make_search_response(query)

    monkeypatch.setattr(NLSearchService, "search", fake_search)

    response = client.get("/api/v1/search", params={"q": "piano", "force_skip_tier5": True})
    assert response.status_code == 403


def test_search_admin_flags_allow_admin(
    client,
    auth_headers_admin,
    monkeypatch,
) -> None:
    async def fake_search(self, query: str, **kwargs) -> NLSearchResponse:
        return _make_search_response(query)

    monkeypatch.setattr(NLSearchService, "search", fake_search)
    monkeypatch.setattr(
        "app.routes.v1.search.get_search_inflight_count",
        AsyncMock(return_value=100),
    )

    response = client.get(
        "/api/v1/search",
        params={"q": "piano", "force_skip_tier5": True},
        headers=auth_headers_admin,
    )
    assert response.status_code == 200


def test_search_health_endpoint(client, monkeypatch) -> None:
    fake_cache = FakeCacheService(cached={"search:response:version": "1"})
    monkeypatch.setattr(fake_cache, "get", AsyncMock(return_value="1"))

    with _override_cache_service(fake_cache):
        response = client.get("/api/v1/search/health")

    assert response.status_code == 200
    data = response.json()
    assert data["components"]["cache"]["available"] is True


def test_search_analytics_endpoints(client, db, auth_headers_admin) -> None:
    repo = SearchAnalyticsRepository(db)
    query_id_1 = generate_ulid()
    query_id_2 = generate_ulid()
    repo.nl_log_search_query(
        original_query="piano lessons",
        normalized_query={"service_query": "piano", "location": "Manhattan"},
        parsing_mode="regex",
        parsing_latency_ms=5,
        result_count=3,
        top_result_ids=[],
        total_latency_ms=42,
        cache_hit=False,
        degraded=False,
        query_id=query_id_1,
    )
    repo.nl_log_search_query(
        original_query="obscure query",
        normalized_query={"service_query": "obscure"},
        parsing_mode="regex",
        parsing_latency_ms=5,
        result_count=0,
        top_result_ids=[],
        total_latency_ms=12,
        cache_hit=False,
        degraded=False,
        query_id=query_id_2,
    )

    response = client.get("/api/v1/search/analytics/metrics", headers=auth_headers_admin)
    assert response.status_code == 200
    assert "total_searches" in response.json()

    response = client.get("/api/v1/search/analytics/popular", headers=auth_headers_admin)
    assert response.status_code == 200
    assert "queries" in response.json()

    response = client.get("/api/v1/search/analytics/zero-results", headers=auth_headers_admin)
    assert response.status_code == 200
    assert "queries" in response.json()


def test_search_config_endpoints(client, auth_headers_admin) -> None:
    response = client.get("/api/v1/search/config", headers=auth_headers_admin)
    assert response.status_code == 200
    assert "available_parsing_models" in response.json()

    response = client.put(
        "/api/v1/search/config",
        json={"parsing_model": "gpt-4o-mini", "parsing_timeout_ms": 1200},
        headers=auth_headers_admin,
    )
    assert response.status_code == 200
    assert response.json()["parsing_model"] == "gpt-4o-mini"

    response = client.put(
        "/api/v1/search/config",
        json={"embedding_model": "text-embedding-3-large"},
        headers=auth_headers_admin,
    )
    assert response.status_code == 400

    response = client.post("/api/v1/search/config/reset", headers=auth_headers_admin)
    assert response.status_code == 200
    assert response.json()["status"] == "reset"


def test_search_click_endpoint(client, db, test_instructor, auth_headers_admin) -> None:
    repo = SearchAnalyticsRepository(db)
    query_id = generate_ulid()
    query_id = repo.nl_log_search_query(
        original_query="guitar lessons",
        normalized_query={"service_query": "guitar"},
        parsing_mode="regex",
        parsing_latency_ms=2,
        result_count=1,
        top_result_ids=[],
        total_latency_ms=20,
        cache_hit=False,
        degraded=False,
        query_id=query_id,
    )

    profile = (
        db.query(InstructorProfile)
        .filter(InstructorProfile.user_id == test_instructor.id)
        .first()
    )
    assert profile is not None
    service = (
        db.query(InstructorService)
        .filter(InstructorService.instructor_profile_id == profile.id)
        .first()
    )
    assert service is not None

    response = client.post(
        "/api/v1/search/click",
        json={
            "search_query_id": query_id,
            "service_id": service.id,
            "instructor_id": test_instructor.id,
            "position": 1,
            "action": "view",
        },
        headers=auth_headers_admin,
    )
    assert response.status_code == 200
    assert response.json()["click_id"]


def test_search_click_endpoint_requires_fields(client) -> None:
    response = client.post("/api/v1/search/click")
    assert response.status_code == 422
