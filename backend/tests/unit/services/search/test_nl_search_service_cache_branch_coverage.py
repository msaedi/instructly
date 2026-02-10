"""Additional cache/timer branch coverage for nl_search_service module helpers."""

from __future__ import annotations

from unittest.mock import patch

import app.services.search.nl_search_service as nl_mod


def setup_function() -> None:
    nl_mod._subcategory_filter_cache.clear()


def test_subcategory_cache_get_miss_and_hit_paths():
    hit, value = nl_mod._get_cached_subcategory_filter_value("missing")
    assert hit is False
    assert value is None

    nl_mod._set_cached_subcategory_filter_value("k1", {"v": 1})
    hit, value = nl_mod._get_cached_subcategory_filter_value("k1")
    assert hit is True
    assert value == {"v": 1}


def test_subcategory_cache_expired_entries_are_removed(monkeypatch):
    monkeypatch.setattr(nl_mod, "SUBCATEGORY_FILTER_CACHE_TTL_SECONDS", 10)

    with patch("app.services.search.nl_search_service.time.monotonic", return_value=0):
        nl_mod._set_cached_subcategory_filter_value("k1", "v1")

    with patch("app.services.search.nl_search_service.time.monotonic", return_value=20):
        hit, value = nl_mod._get_cached_subcategory_filter_value("k1")

    assert hit is False
    assert value is None
    assert "k1" not in nl_mod._subcategory_filter_cache


def test_subcategory_cache_bounded_eviction_trims_oldest_half(monkeypatch):
    monkeypatch.setattr(nl_mod, "SUBCATEGORY_FILTER_CACHE_MAX_ENTRIES", 2)
    monkeypatch.setattr(nl_mod, "SUBCATEGORY_FILTER_CACHE_TTL_SECONDS", 1000)

    with patch(
        "app.services.search.nl_search_service.time.monotonic",
        side_effect=[1, 2, 3],
    ):
        nl_mod._set_cached_subcategory_filter_value("a", 1)
        nl_mod._set_cached_subcategory_filter_value("b", 2)
        nl_mod._set_cached_subcategory_filter_value("c", 3)

    # Oldest entry should be trimmed when capacity is exceeded.
    assert len(nl_mod._subcategory_filter_cache) <= 2
    assert "c" in nl_mod._subcategory_filter_cache


def test_pipeline_timer_end_stage_is_noop_without_start():
    timer = nl_mod.PipelineTimer()

    timer.end_stage(status="success")

    assert timer.stages == []


def test_pipeline_timer_records_stage_after_start():
    timer = nl_mod.PipelineTimer()

    timer.start_stage("burst-1")
    timer.end_stage(status="success", details={"count": 1})

    assert len(timer.stages) == 1
    assert timer.stages[0]["name"] == "burst-1"
    assert timer.stages[0]["details"]["count"] == 1
