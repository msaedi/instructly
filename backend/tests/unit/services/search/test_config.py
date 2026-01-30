# backend/tests/unit/services/search/test_config.py
"""
Comprehensive unit tests for search/config.py.

Targets missed lines:
- 72: to_dict method
- 101: get_search_config double-check locking
- 146-169: All update_search_config branches

Bug Analysis:
- No critical bugs found
- Config updates properly sync to settings for location model/timeout
- Thread safety is handled with lock
- Hot-reload is intentionally ephemeral (reset on restart)
"""
from __future__ import annotations

from threading import Thread

from app.core.config import settings
from app.services.search import config as config_module
from app.services.search.config import (
    AVAILABLE_EMBEDDING_MODELS,
    AVAILABLE_PARSING_MODELS,
    SearchConfig,
    get_search_config,
    reset_search_config,
    update_search_config,
)


class TestSearchConfigDefaults:
    """Tests for SearchConfig default values."""

    def test_default_values(self) -> None:
        """Test that SearchConfig has sensible defaults."""
        config = SearchConfig()

        assert config.parsing_model == "gpt-5-nano"
        assert config.parsing_timeout_ms == 1000
        assert config.embedding_model == "text-embedding-3-small"
        assert config.embedding_timeout_ms == 2000
        assert config.location_model == "gpt-4o-mini"
        assert config.location_timeout_ms == 3000
        assert config.max_retries == 2
        assert config.search_budget_ms == 500
        assert config.high_load_budget_ms == 300
        assert config.high_load_threshold == 10
        assert config.uncached_concurrency == 6


class TestSearchConfigFromEnv:
    """Tests for SearchConfig.from_env method."""

    def test_from_env_uses_defaults_when_not_set(self, monkeypatch) -> None:
        """Test from_env uses defaults when env vars are not set."""
        # Clear any existing env vars
        for var in [
            "OPENAI_PARSING_MODEL",
            "OPENAI_PARSING_TIMEOUT_MS",
            "OPENAI_EMBEDDING_MODEL",
            "OPENAI_EMBEDDING_TIMEOUT_MS",
            "OPENAI_LOCATION_MODEL",
            "OPENAI_LOCATION_TIMEOUT_MS",
            "OPENAI_MAX_RETRIES",
            "SEARCH_BUDGET_MS",
            "SEARCH_HIGH_LOAD_BUDGET_MS",
            "SEARCH_HIGH_LOAD_THRESHOLD",
            "UNCACHED_SEARCH_CONCURRENCY",
        ]:
            monkeypatch.delenv(var, raising=False)

        config = SearchConfig.from_env()

        assert config.parsing_model == "gpt-5-nano"
        assert config.parsing_timeout_ms == 1000

    def test_from_env_reads_all_env_vars(self, monkeypatch) -> None:
        """Test from_env reads all environment variables."""
        monkeypatch.setenv("OPENAI_PARSING_MODEL", "gpt-4o")
        monkeypatch.setenv("OPENAI_PARSING_TIMEOUT_MS", "1500")
        monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")
        monkeypatch.setenv("OPENAI_EMBEDDING_TIMEOUT_MS", "2500")
        monkeypatch.setenv("OPENAI_LOCATION_MODEL", "gpt-4o-mini-custom")
        monkeypatch.setenv("OPENAI_LOCATION_TIMEOUT_MS", "3500")
        monkeypatch.setenv("OPENAI_MAX_RETRIES", "5")
        monkeypatch.setenv("SEARCH_BUDGET_MS", "600")
        monkeypatch.setenv("SEARCH_HIGH_LOAD_BUDGET_MS", "400")
        monkeypatch.setenv("SEARCH_HIGH_LOAD_THRESHOLD", "15")
        monkeypatch.setenv("UNCACHED_SEARCH_CONCURRENCY", "8")

        config = SearchConfig.from_env()

        assert config.parsing_model == "gpt-4o"
        assert config.parsing_timeout_ms == 1500
        assert config.embedding_model == "text-embedding-3-large"
        assert config.embedding_timeout_ms == 2500
        assert config.location_model == "gpt-4o-mini-custom"
        assert config.location_timeout_ms == 3500
        assert config.max_retries == 5
        assert config.search_budget_ms == 600
        assert config.high_load_budget_ms == 400
        assert config.high_load_threshold == 15
        assert config.uncached_concurrency == 8


class TestSearchConfigToDict:
    """Tests for SearchConfig.to_dict method (line 72)."""

    def test_to_dict_returns_all_fields(self) -> None:
        """Test to_dict returns all configuration fields."""
        config = SearchConfig(
            parsing_model="gpt-4o",
            parsing_timeout_ms=1500,
            embedding_model="text-embedding-3-large",
            embedding_timeout_ms=2500,
            location_model="gpt-4o-mini",
            location_timeout_ms=3500,
            max_retries=3,
            search_budget_ms=600,
            high_load_budget_ms=400,
            high_load_threshold=15,
            uncached_concurrency=8,
        )

        result = config.to_dict()

        assert isinstance(result, dict)
        assert result["parsing_model"] == "gpt-4o"
        assert result["parsing_timeout_ms"] == 1500
        assert result["embedding_model"] == "text-embedding-3-large"
        assert result["embedding_timeout_ms"] == 2500
        assert result["location_model"] == "gpt-4o-mini"
        assert result["location_timeout_ms"] == 3500
        assert result["max_retries"] == 3
        assert result["search_budget_ms"] == 600
        assert result["high_load_budget_ms"] == 400
        assert result["high_load_threshold"] == 15
        assert result["uncached_concurrency"] == 8

    def test_to_dict_has_correct_keys(self) -> None:
        """Test to_dict has exactly the expected keys."""
        config = SearchConfig()
        result = config.to_dict()

        expected_keys = {
            "parsing_model",
            "parsing_timeout_ms",
            "embedding_model",
            "embedding_timeout_ms",
            "location_model",
            "location_timeout_ms",
            "max_retries",
            "search_budget_ms",
            "high_load_budget_ms",
            "high_load_threshold",
            "uncached_concurrency",
        }

        assert set(result.keys()) == expected_keys


class TestGetSearchConfig:
    """Tests for get_search_config singleton function."""

    def test_get_search_config_creates_singleton(self) -> None:
        """Test that get_search_config returns the same instance."""
        config_module._config = None

        config1 = get_search_config()
        config2 = get_search_config()

        assert config1 is config2

        # Cleanup
        config_module._config = None

    def test_get_search_config_double_check_locking(self) -> None:
        """Test thread safety with double-check locking (line 101)."""
        config_module._config = None

        configs = []

        def get_config():
            configs.append(get_search_config())

        threads = [Thread(target=get_config) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All threads should get the same instance
        assert len(configs) == 10
        assert all(c is configs[0] for c in configs)

        # Cleanup
        config_module._config = None


class TestUpdateSearchConfig:
    """Tests for update_search_config function (lines 146-169)."""

    def setup_method(self) -> None:
        """Reset config before each test."""
        config_module._config = None

    def teardown_method(self) -> None:
        """Reset config after each test."""
        config_module._config = None

    def test_update_parsing_model(self) -> None:
        """Test updating parsing_model (line 146-147)."""
        updated = update_search_config(parsing_model="gpt-4o")

        assert updated.parsing_model == "gpt-4o"

    def test_update_parsing_timeout_ms(self) -> None:
        """Test updating parsing_timeout_ms (line 148-149)."""
        updated = update_search_config(parsing_timeout_ms=1500)

        assert updated.parsing_timeout_ms == 1500

    def test_update_embedding_model(self) -> None:
        """Test updating embedding_model (line 150-151)."""
        updated = update_search_config(embedding_model="text-embedding-3-large")

        assert updated.embedding_model == "text-embedding-3-large"

    def test_update_embedding_timeout_ms(self) -> None:
        """Test updating embedding_timeout_ms (line 152-153)."""
        updated = update_search_config(embedding_timeout_ms=3000)

        assert updated.embedding_timeout_ms == 3000

    def test_update_location_model_syncs_to_settings(self) -> None:
        """Test updating location_model also updates settings (lines 154-156)."""
        original_model = settings.openai_location_model

        try:
            updated = update_search_config(location_model="gpt-4o")

            assert updated.location_model == "gpt-4o"
            assert settings.openai_location_model == "gpt-4o"
        finally:
            settings.openai_location_model = original_model

    def test_update_location_timeout_ms_syncs_to_settings(self) -> None:
        """Test updating location_timeout_ms also updates settings (lines 157-159)."""
        original_timeout = settings.openai_location_timeout_ms

        try:
            updated = update_search_config(location_timeout_ms=4000)

            assert updated.location_timeout_ms == 4000
            assert settings.openai_location_timeout_ms == 4000
        finally:
            settings.openai_location_timeout_ms = original_timeout

    def test_update_max_retries(self) -> None:
        """Test updating max_retries (lines 160-161)."""
        updated = update_search_config(max_retries=5)

        assert updated.max_retries == 5

    def test_update_search_budget_ms(self) -> None:
        """Test updating search_budget_ms (lines 162-163)."""
        updated = update_search_config(search_budget_ms=700)

        assert updated.search_budget_ms == 700

    def test_update_high_load_budget_ms(self) -> None:
        """Test updating high_load_budget_ms (lines 164-165)."""
        updated = update_search_config(high_load_budget_ms=250)

        assert updated.high_load_budget_ms == 250

    def test_update_high_load_threshold(self) -> None:
        """Test updating high_load_threshold (lines 166-167)."""
        updated = update_search_config(high_load_threshold=20)

        assert updated.high_load_threshold == 20

    def test_update_uncached_concurrency(self) -> None:
        """Test updating uncached_concurrency (lines 168-169)."""
        updated = update_search_config(uncached_concurrency=10)

        assert updated.uncached_concurrency == 10

    def test_update_multiple_fields(self) -> None:
        """Test updating multiple fields at once."""
        updated = update_search_config(
            parsing_model="gpt-4o",
            parsing_timeout_ms=2000,
            embedding_model="text-embedding-3-large",
            max_retries=4,
        )

        assert updated.parsing_model == "gpt-4o"
        assert updated.parsing_timeout_ms == 2000
        assert updated.embedding_model == "text-embedding-3-large"
        assert updated.max_retries == 4

    def test_update_none_values_are_skipped(self) -> None:
        """Test that None values don't override existing config."""
        # Set initial config
        update_search_config(parsing_model="initial-model")

        # Update with None (should be ignored)
        updated = update_search_config(
            parsing_model=None,
            max_retries=3,
        )

        assert updated.parsing_model == "initial-model"
        assert updated.max_retries == 3

    def test_update_creates_config_if_not_exists(self) -> None:
        """Test update_search_config creates config from env if not exists (line 143-144)."""
        config_module._config = None

        updated = update_search_config(max_retries=10)

        assert updated is not None
        assert updated.max_retries == 10


class TestResetSearchConfig:
    """Tests for reset_search_config function."""

    def test_reset_returns_fresh_config(self) -> None:
        """Test reset_search_config creates fresh config from env."""
        config_module._config = None

        # Modify config
        update_search_config(parsing_model="modified-model")

        # Reset should return to env defaults
        reset = reset_search_config()

        # Should be fresh from env (default is gpt-5-nano)
        assert reset.parsing_model == "gpt-5-nano"

        # Cleanup
        config_module._config = None

    def test_reset_syncs_location_settings(self) -> None:
        """Test reset also syncs location settings back."""
        config_module._config = None
        original_model = settings.openai_location_model
        original_timeout = settings.openai_location_timeout_ms

        try:
            # Modify settings via update
            update_search_config(location_model="gpt-4o", location_timeout_ms=5000)

            # Reset should restore
            reset = reset_search_config()

            # Settings should be updated to match reset config
            assert settings.openai_location_model == reset.location_model
            assert settings.openai_location_timeout_ms == reset.location_timeout_ms
        finally:
            settings.openai_location_model = original_model
            settings.openai_location_timeout_ms = original_timeout
            config_module._config = None


class TestAvailableModels:
    """Tests for available model constants."""

    def test_available_parsing_models_structure(self) -> None:
        """Test AVAILABLE_PARSING_MODELS has correct structure."""
        assert len(AVAILABLE_PARSING_MODELS) > 0

        for model in AVAILABLE_PARSING_MODELS:
            assert "id" in model
            assert "name" in model
            assert "description" in model
            assert isinstance(model["id"], str)
            assert isinstance(model["name"], str)
            assert isinstance(model["description"], str)

    def test_available_embedding_models_structure(self) -> None:
        """Test AVAILABLE_EMBEDDING_MODELS has correct structure."""
        assert len(AVAILABLE_EMBEDDING_MODELS) > 0

        for model in AVAILABLE_EMBEDDING_MODELS:
            assert "id" in model
            assert "name" in model
            assert "description" in model

    def test_parsing_models_include_recommended(self) -> None:
        """Test that GPT-5 Nano is included as recommended model."""
        model_ids = [m["id"] for m in AVAILABLE_PARSING_MODELS]
        assert "gpt-5-nano" in model_ids

    def test_embedding_models_include_recommended(self) -> None:
        """Test that text-embedding-3-small is included."""
        model_ids = [m["id"] for m in AVAILABLE_EMBEDDING_MODELS]
        assert "text-embedding-3-small" in model_ids


class TestConfigThreadSafety:
    """Tests for configuration thread safety."""

    def test_concurrent_updates_are_safe(self) -> None:
        """Test that concurrent updates don't cause race conditions."""
        config_module._config = None

        results = []

        def update_config(value: int):
            updated = update_search_config(max_retries=value)
            results.append(updated.max_retries)

        threads = [Thread(target=update_config, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All operations should complete without error
        assert len(results) == 10
        # Final value should be one of the values set
        final_config = get_search_config()
        assert final_config.max_retries in range(10)

        # Cleanup
        config_module._config = None

    def test_concurrent_get_and_update(self) -> None:
        """Test concurrent get and update operations."""
        config_module._config = None

        configs = []
        updates = []

        def get_config():
            configs.append(get_search_config())

        def update_config():
            updates.append(update_search_config(max_retries=99))

        threads = []
        for i in range(5):
            threads.append(Thread(target=get_config))
            threads.append(Thread(target=update_config))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All operations should complete
        assert len(configs) == 5
        assert len(updates) == 5

        # Cleanup
        config_module._config = None
