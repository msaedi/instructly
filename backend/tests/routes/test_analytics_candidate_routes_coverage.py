from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.routes.v1 import analytics as routes


class _ServiceStub:
    def get_candidate_summary(self, _days):
        return {
            "total_candidates": 10,
            "events_with_candidates": 5,
            "avg_candidates_per_event": 2.0,
            "zero_result_events_with_candidates": 1,
            "source_breakdown": {"llm": 7},
        }

    def get_candidate_category_trends(self, _days):
        return [{"date": "2024-01-01", "category": "music", "count": 3}]

    def get_candidate_top_services(self, _days, _limit):
        return [
            {
                "service_catalog_id": "svc-1",
                "service_name": "Piano",
                "category_name": "Music",
                "candidate_count": 4,
                "avg_score": 0.9,
                "avg_position": 1.2,
                "active_instructors": 2,
                "opportunity_score": 0.8,
            }
        ]

    def get_candidate_score_distribution(self, _days):
        return {
            "gte_0_90": 1,
            "gte_0_80_lt_0_90": 2,
            "gte_0_70_lt_0_80": 3,
            "lt_0_70": 4,
        }

    def get_candidate_service_queries(self, _service_catalog_id, _days, _limit):
        return [
            {
                "searched_at": "2024-01-02",
                "search_query": "piano lessons",
                "results_count": 5,
                "position": 1,
                "score": 0.91,
                "source": "llm",
            }
        ]


async def _to_thread(func, *args, **kwargs):
    return func(*args, **kwargs)


@pytest.mark.asyncio
async def test_candidates_summary(monkeypatch):
    monkeypatch.setattr(routes, "get_search_analytics_service", lambda _db=None: _ServiceStub())
    monkeypatch.setattr(routes.asyncio, "to_thread", _to_thread)

    response = await routes.candidates_summary(
        current_user=SimpleNamespace(),
        service=_ServiceStub(),
    )

    assert response.total_candidates == 10
    assert response.source_breakdown["llm"] == 7


@pytest.mark.asyncio
async def test_candidates_category_trends(monkeypatch):
    monkeypatch.setattr(routes, "get_search_analytics_service", lambda _db=None: _ServiceStub())
    monkeypatch.setattr(routes.asyncio, "to_thread", _to_thread)

    response = await routes.candidates_category_trends(
        current_user=SimpleNamespace(),
        service=_ServiceStub(),
    )

    assert response.root[0].category == "music"
    assert response.root[0].count == 3


@pytest.mark.asyncio
async def test_candidates_top_services(monkeypatch):
    monkeypatch.setattr(routes, "get_search_analytics_service", lambda _db=None: _ServiceStub())
    monkeypatch.setattr(routes.asyncio, "to_thread", _to_thread)

    response = await routes.candidates_top_services(
        current_user=SimpleNamespace(),
        service=_ServiceStub(),
    )

    assert response.root[0].service_catalog_id == "svc-1"
    assert response.root[0].candidate_count == 4


@pytest.mark.asyncio
async def test_candidates_score_distribution(monkeypatch):
    monkeypatch.setattr(routes, "get_search_analytics_service", lambda _db=None: _ServiceStub())
    monkeypatch.setattr(routes.asyncio, "to_thread", _to_thread)

    response = await routes.candidates_score_distribution(
        current_user=SimpleNamespace(),
        service=_ServiceStub(),
    )

    assert response.gte_0_90 == 1
    assert response.lt_0_70 == 4


@pytest.mark.asyncio
async def test_candidate_service_queries(monkeypatch):
    monkeypatch.setattr(routes, "get_search_analytics_service", lambda _db=None: _ServiceStub())
    monkeypatch.setattr(routes.asyncio, "to_thread", _to_thread)

    response = await routes.candidate_service_queries(
        service_catalog_id="svc-1",
        current_user=SimpleNamespace(),
        analytics_service=_ServiceStub(),
    )

    assert response.root[0].search_query == "piano lessons"
    assert response.root[0].source == "llm"
