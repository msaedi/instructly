from __future__ import annotations

import asyncio
from contextlib import contextmanager
import math
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from app.schemas.search_context import SearchUserContext
from app.services.search_history_service import SearchHistoryService


@contextmanager
def _tx():
    yield


def _service() -> SearchHistoryService:
    service = SearchHistoryService.__new__(SearchHistoryService)
    service.db = MagicMock()
    service.repository = MagicMock()
    service.event_repository = MagicMock()
    service.interaction_repository = MagicMock()
    service.geolocation_service = MagicMock()
    service.device_tracking_service = MagicMock()
    service.transaction = Mock(return_value=_tx())
    return service


@pytest.mark.asyncio
async def test_record_search_requires_user_or_guest():
    service = _service()

    with pytest.raises(ValueError, match="either user_id or guest_session_id"):
        await service.record_search(query="guitar")


def test_normalize_search_query_handles_empty_input():
    service = _service()
    assert service.normalize_search_query("") == ""
    assert service.normalize_search_query("  Piano  ") == "piano"


@pytest.mark.asyncio
async def test_record_search_impl_handles_analytics_side_effect_failures(monkeypatch):
    service = _service()
    context = SearchUserContext.from_user("user-1")
    upserted = SimpleNamespace(search_count=2)
    service.repository.upsert_search.return_value = upserted
    service._enforce_search_limit = Mock()
    service.geolocation_service.get_location_from_ip.side_effect = RuntimeError("geo-down")
    service.device_tracking_service.parse_user_agent.return_value = {"raw": "ua"}
    service.device_tracking_service.format_for_analytics.return_value = {"device": {}}
    service.event_repository.get_previous_search_event.return_value = None
    service.event_repository.create_event.return_value = SimpleNamespace(id="event-1")
    service.event_repository.bulk_insert_candidates.side_effect = RuntimeError("bulk-down")

    async def _to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", _to_thread)

    result = await service._record_search_impl(
        context,
        {"search_query": "Piano", "search_type": "natural_language", "results_count": 3},
        request_ip="127.0.0.1",
        user_agent="Mozilla/5.0",
        device_context={"device_type": "mobile", "viewport_size": "375x812"},
        observability_candidates=[{"id": "svc_1", "score": 0.9}],
    )

    assert result is upserted
    assert getattr(result, "search_event_id") == "event-1"
    service.event_repository.bulk_insert_candidates.assert_called_once()


@pytest.mark.asyncio
async def test_record_search_impl_guest_returning_lookup_branch(monkeypatch):
    service = _service()
    context = SearchUserContext.from_guest("guest-1")
    upserted = SimpleNamespace(search_count=1)
    service.repository.upsert_search.return_value = upserted
    service._enforce_search_limit = Mock()
    service.event_repository.get_previous_search_event.return_value = SimpleNamespace(id="old")
    service.event_repository.create_event.return_value = SimpleNamespace(id="event-guest")

    async def _to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", _to_thread)

    result = await service._record_search_impl(
        context,
        {"search_query": "drums", "search_type": "natural_language", "results_count": 2},
    )

    assert result is upserted
    guest_lookup_call = service.event_repository.get_previous_search_event.call_args
    assert guest_lookup_call.args[0] is None
    assert guest_lookup_call.args[1] == "guest-1"


@pytest.mark.asyncio
async def test_record_search_impl_rethrows_repository_errors(monkeypatch):
    service = _service()
    context = SearchUserContext.from_user("user-1")
    service.repository.upsert_search.side_effect = RuntimeError("db-down")

    async def _to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", _to_thread)

    with pytest.raises(RuntimeError, match="db-down"):
        await service._record_search_impl(
            context,
            {"search_query": "violin", "search_type": "natural_language"},
        )


def test_get_recent_searches_requires_identity_context():
    service = _service()

    with pytest.raises(ValueError, match="either user_id, guest_session_id, or context"):
        service.get_recent_searches()


def test_delete_search_guest_and_missing_identity_paths():
    service = _service()

    assert service.delete_search(search_id=None) is False

    service.repository.soft_delete_guest_search.return_value = True
    assert service.delete_search(guest_session_id="guest-1", search_id="search-1") is True
    service.repository.soft_delete_guest_search.assert_called_once()

    assert service.delete_search(search_id="search-2") is False


def test_convert_guest_searches_to_user_returns_zero_on_errors():
    service = _service()
    service.repository.get_guest_searches_for_conversion.side_effect = RuntimeError("repo-down")

    converted = service.convert_guest_searches_to_user("guest-1", "user-1")

    assert converted == 0


def test_track_interaction_enforces_strictly_increasing_timing():
    service = _service()
    service.event_repository.get_search_event_by_id.return_value = SimpleNamespace(session_id="sess-1")
    service.interaction_repository.get_latest_time_to_interaction.return_value = 0.5
    service.interaction_repository.create_interaction.return_value = SimpleNamespace(id="int-1")

    interaction = service.track_interaction(
        search_event_id="event-1",
        interaction_type="click",
        time_to_interaction=0.5,
        instructor_id="instr-1",
    )

    assert interaction.id == "int-1"
    payload = service.interaction_repository.create_interaction.call_args.args[0]
    assert payload["time_to_interaction"] > 0.5
    assert math.isclose(payload["time_to_interaction"], math.nextafter(0.5, math.inf))
