from __future__ import annotations

from types import SimpleNamespace

from app.services.search.location_learning_click_service import LocationLearningClickService


def test_capture_location_learning_click_skips_missing_data(monkeypatch) -> None:
    service = LocationLearningClickService(SimpleNamespace())

    service.search_query_repo = SimpleNamespace(get_normalized_query=lambda _id: None)
    service.service_area_repo = SimpleNamespace(get_primary_active_neighborhood_id=lambda _id: "nbhd")
    service.unresolved_repo = SimpleNamespace(record_click=lambda *args, **kwargs: None)
    service.learning_service = SimpleNamespace(maybe_learn_from_query=lambda _text: None)

    service.capture_location_learning_click(search_query_id="q1", instructor_user_id="u1")

    service.search_query_repo = SimpleNamespace(
        get_normalized_query=lambda _id: {"location_not_found": False}
    )
    service.capture_location_learning_click(search_query_id="q1", instructor_user_id="u1")

    service.search_query_repo = SimpleNamespace(
        get_normalized_query=lambda _id: {"location_not_found": True, "location": ""}
    )
    service.capture_location_learning_click(search_query_id="q1", instructor_user_id="u1")

    service.search_query_repo = SimpleNamespace(
        get_normalized_query=lambda _id: {"location_not_found": True, "location": "SoHo"}
    )
    service.service_area_repo = SimpleNamespace(get_primary_active_neighborhood_id=lambda _id: None)
    service.capture_location_learning_click(search_query_id="q1", instructor_user_id="u1")


def test_capture_location_learning_click_records(monkeypatch) -> None:
    service = LocationLearningClickService(SimpleNamespace())

    service.search_query_repo = SimpleNamespace(
        get_normalized_query=lambda _id: {"location_not_found": True, "location": "SoHo"}
    )
    service.service_area_repo = SimpleNamespace(
        get_primary_active_neighborhood_id=lambda _id: "nbhd-1"
    )

    recorded = {}

    def _record_click(location_text, region_boundary_id=None, original_query=None):
        recorded["location_text"] = location_text
        recorded["region_boundary_id"] = region_boundary_id
        recorded["original_query"] = original_query

    service.unresolved_repo = SimpleNamespace(record_click=_record_click)

    learned = {}

    def _maybe_learn(query):
        learned["query"] = query

    service.learning_service = SimpleNamespace(maybe_learn_from_query=_maybe_learn)

    service.capture_location_learning_click(search_query_id="q1", instructor_user_id="u1")

    assert recorded["region_boundary_id"] == "nbhd-1"
    assert learned["query"] == "SoHo"
