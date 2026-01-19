from __future__ import annotations

from app.core.config import settings
from app.services.search import config as config_module
from app.services.search.config import (
    SearchConfig,
    get_search_config,
    reset_search_config,
    update_search_config,
)


def test_search_config_from_env(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_PARSING_MODEL", "gpt-test")
    monkeypatch.setenv("OPENAI_PARSING_TIMEOUT_MS", "1500")
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")
    monkeypatch.setenv("OPENAI_EMBEDDING_TIMEOUT_MS", "2500")
    monkeypatch.setenv("OPENAI_MAX_RETRIES", "4")
    monkeypatch.setenv("SEARCH_BUDGET_MS", "600")
    monkeypatch.setenv("SEARCH_HIGH_LOAD_BUDGET_MS", "400")
    monkeypatch.setenv("SEARCH_HIGH_LOAD_THRESHOLD", "12")
    monkeypatch.setenv("UNCACHED_SEARCH_CONCURRENCY", "9")

    cfg = SearchConfig.from_env()
    assert cfg.parsing_model == "gpt-test"
    assert cfg.parsing_timeout_ms == 1500
    assert cfg.embedding_model == "text-embedding-3-large"
    assert cfg.embedding_timeout_ms == 2500
    assert cfg.max_retries == 4
    assert cfg.search_budget_ms == 600
    assert cfg.high_load_budget_ms == 400
    assert cfg.high_load_threshold == 12
    assert cfg.uncached_concurrency == 9


def test_get_search_config_is_singleton(monkeypatch) -> None:
    config_module._config = None
    cfg_first = get_search_config()
    cfg_second = get_search_config()
    assert cfg_first is cfg_second
    config_module._config = None


def test_update_and_reset_search_config(monkeypatch) -> None:
    config_module._config = None
    original_model = settings.openai_location_model
    original_timeout = settings.openai_location_timeout_ms

    try:
        updated = update_search_config(
            parsing_model="gpt-4o-mini",
            parsing_timeout_ms=1200,
            location_model="gpt-4o",
            location_timeout_ms=3500,
            max_retries=1,
        )
        assert updated.parsing_model == "gpt-4o-mini"
        assert updated.parsing_timeout_ms == 1200
        assert updated.location_model == "gpt-4o"
        assert updated.location_timeout_ms == 3500
        assert updated.max_retries == 1
        assert settings.openai_location_model == "gpt-4o"
        assert settings.openai_location_timeout_ms == 3500

        reset = reset_search_config()
        assert reset.location_model == settings.openai_location_model
        assert reset.location_timeout_ms == settings.openai_location_timeout_ms
    finally:
        settings.openai_location_model = original_model
        settings.openai_location_timeout_ms = original_timeout
        config_module._config = None
