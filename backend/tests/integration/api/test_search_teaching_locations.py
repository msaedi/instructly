from __future__ import annotations

from fastapi.testclient import TestClient

from app.schemas.nl_search import (
    InstructorSummary,
    NLSearchMeta,
    NLSearchResponse,
    NLSearchResultItem,
    ParsedQueryInfo,
    RatingSummary,
    ServiceMatch,
)


def test_search_results_include_teaching_locations(client: TestClient, monkeypatch) -> None:
    async def fake_search(*_args, **_kwargs) -> NLSearchResponse:
        instructor = InstructorSummary(
            id="inst-1",
            first_name="Test",
            last_initial="I",
            profile_picture_url=None,
            bio_snippet=None,
            verified=False,
            is_founding_instructor=False,
            years_experience=5,
            teaching_locations=[
                {
                    "approx_lat": 40.7128,
                    "approx_lng": -74.0060,
                    "neighborhood": "Lower East Side",
                }
            ],
        )

        result = NLSearchResultItem(
            instructor_id="inst-1",
            instructor=instructor,
            rating=RatingSummary(average=4.8, count=12),
            coverage_areas=["Lower East Side"],
            best_match=ServiceMatch(
                service_id="svc-1",
                service_catalog_id="cat-1",
                name="Piano Lessons",
                description=None,
                price_per_hour=60,
                relevance_score=0.9,
            ),
            other_matches=[],
            total_matching_services=1,
            relevance_score=0.9,
            distance_km=None,
            distance_mi=None,
        )

        meta = NLSearchMeta(
            query="piano lessons",
            parsed=ParsedQueryInfo(service_query="piano lessons"),
            total_results=1,
            limit=20,
            latency_ms=5,
            cache_hit=False,
            degraded=False,
            parsing_mode="regex",
        )

        return NLSearchResponse(results=[result], meta=meta)

    monkeypatch.setattr("app.routes.v1.search.NLSearchService.search", fake_search)

    response = client.get("/api/v1/search", params={"q": "piano lessons"})
    assert response.status_code == 200

    data = response.json()
    assert data["results"], "Expected at least one search result"
    instructor = data["results"][0]["instructor"]
    locations = instructor.get("teaching_locations", [])
    assert locations, "Expected teaching locations in search result"
    location = locations[0]
    assert "approx_lat" in location
    assert "approx_lng" in location
    assert "address" not in location
