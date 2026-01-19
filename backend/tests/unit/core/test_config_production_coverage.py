"""
Tests for config_production.py - targeting CI coverage gaps.
Coverage for production-optimized configuration settings.
"""
import os
from unittest.mock import patch


class TestDatabasePoolConfig:
    """Tests for DATABASE_POOL_CONFIG settings."""

    def test_default_pool_size(self):
        """Test default pool size is 5."""
        with patch.dict(os.environ, {}, clear=False):
            # Re-import to get fresh config
            import importlib

            import app.core.config_production as config_mod
            importlib.reload(config_mod)

            # Default should be 5 when env var not set
            assert config_mod.DATABASE_POOL_CONFIG["pool_size"] == int(
                os.getenv("DATABASE_POOL_SIZE", "5")
            )

    def test_pool_config_has_required_keys(self):
        """Test that pool config has all required settings."""
        from app.core.config_production import DATABASE_POOL_CONFIG

        required_keys = [
            "pool_size",
            "max_overflow",
            "pool_timeout",
            "pool_recycle",
            "pool_pre_ping",
            "pool_use_lifo",
            "future",
            "echo_pool",
            "connect_args",
        ]

        for key in required_keys:
            assert key in DATABASE_POOL_CONFIG, f"Missing key: {key}"

    def test_pool_recycle_less_than_supavisor_timeout(self):
        """Test pool_recycle is set correctly for Supavisor compatibility."""
        from app.core.config_production import DATABASE_POOL_CONFIG

        # Supavisor times out at ~60s, pool_recycle should be less
        assert DATABASE_POOL_CONFIG["pool_recycle"] < 60

    def test_connect_args_has_ssl_required(self):
        """Test SSL is required in connect args."""
        from app.core.config_production import DATABASE_POOL_CONFIG

        assert DATABASE_POOL_CONFIG["connect_args"]["sslmode"] == "require"

    def test_connect_args_has_keepalive_settings(self):
        """Test keepalive settings are configured."""
        from app.core.config_production import DATABASE_POOL_CONFIG

        connect_args = DATABASE_POOL_CONFIG["connect_args"]

        assert connect_args["keepalives"] == 1
        assert "keepalives_idle" in connect_args
        assert "keepalives_interval" in connect_args
        assert "keepalives_count" in connect_args

    def test_statement_timeout_is_set(self):
        """Test statement timeout is set in options."""
        from app.core.config_production import DATABASE_POOL_CONFIG

        options = DATABASE_POOL_CONFIG["connect_args"]["options"]
        assert "statement_timeout" in options


class TestRedisConfig:
    """Tests for REDIS_CONFIG settings."""

    def test_redis_config_has_required_keys(self):
        """Test Redis config has all required settings."""
        from app.core.config_production import REDIS_CONFIG

        required_keys = [
            "max_connections",
            "socket_connect_timeout",
            "socket_timeout",
            "retry_on_timeout",
            "health_check_interval",
            "decode_responses",
            "connection_pool_kwargs",
        ]

        for key in required_keys:
            assert key in REDIS_CONFIG, f"Missing key: {key}"

    def test_redis_retry_on_timeout_enabled(self):
        """Test retry on timeout is enabled."""
        from app.core.config_production import REDIS_CONFIG

        assert REDIS_CONFIG["retry_on_timeout"] is True

    def test_redis_connection_pool_kwargs(self):
        """Test connection pool kwargs are set correctly."""
        from app.core.config_production import REDIS_CONFIG

        pool_kwargs = REDIS_CONFIG["connection_pool_kwargs"]

        assert "max_connections" in pool_kwargs
        assert "retry" in pool_kwargs
        assert pool_kwargs["retry"] == 3


class TestCacheTtlTiers:
    """Tests for CACHE_TTL_TIERS configuration."""

    def test_cache_ttl_tiers_exist(self):
        """Test all cache tiers are defined."""
        from app.core.config_production import CACHE_TTL_TIERS

        assert "hot" in CACHE_TTL_TIERS
        assert "warm" in CACHE_TTL_TIERS
        assert "cold" in CACHE_TTL_TIERS
        assert "static" in CACHE_TTL_TIERS

    def test_cache_ttl_ordering(self):
        """Test cache TTLs are in ascending order by tier."""
        from app.core.config_production import CACHE_TTL_TIERS

        assert CACHE_TTL_TIERS["hot"] < CACHE_TTL_TIERS["warm"]
        assert CACHE_TTL_TIERS["warm"] < CACHE_TTL_TIERS["cold"]
        assert CACHE_TTL_TIERS["cold"] < CACHE_TTL_TIERS["static"]

    def test_hot_cache_is_short(self):
        """Test hot cache TTL is reasonably short (under 5 minutes)."""
        from app.core.config_production import CACHE_TTL_TIERS

        assert CACHE_TTL_TIERS["hot"] <= 300  # 5 minutes


class TestGunicornConfig:
    """Tests for GUNICORN_CONFIG settings."""

    def test_gunicorn_config_has_required_keys(self):
        """Test Gunicorn config has essential settings."""
        from app.core.config_production import GUNICORN_CONFIG

        required_keys = [
            "workers",
            "worker_class",
            "worker_connections",
            "max_requests",
            "max_requests_jitter",
            "timeout",
            "graceful_timeout",
            "keepalive",
            "threads",
        ]

        for key in required_keys:
            assert key in GUNICORN_CONFIG, f"Missing key: {key}"

    def test_worker_class_is_uvicorn(self):
        """Test worker class is set to Uvicorn."""
        from app.core.config_production import GUNICORN_CONFIG

        assert GUNICORN_CONFIG["worker_class"] == "uvicorn.workers.UvicornWorker"

    def test_preload_app_enabled(self):
        """Test preload_app is enabled for memory sharing."""
        from app.core.config_production import GUNICORN_CONFIG

        assert GUNICORN_CONFIG["preload_app"] is True


class TestCeleryWorkerConfig:
    """Tests for CELERY_WORKER_CONFIG settings."""

    def test_celery_config_has_required_keys(self):
        """Test Celery worker config has essential settings."""
        from app.core.config_production import CELERY_WORKER_CONFIG

        required_keys = [
            "concurrency",
            "prefetch_multiplier",
            "max_tasks_per_child",
            "task_compression",
            "result_compression",
            "result_expires",
            "task_time_limit",
            "task_soft_time_limit",
        ]

        for key in required_keys:
            assert key in CELERY_WORKER_CONFIG, f"Missing key: {key}"

    def test_soft_time_limit_less_than_hard_limit(self):
        """Test soft time limit is less than hard time limit."""
        from app.core.config_production import CELERY_WORKER_CONFIG

        assert CELERY_WORKER_CONFIG["task_soft_time_limit"] < CELERY_WORKER_CONFIG["task_time_limit"]

    def test_compression_is_gzip(self):
        """Test compression is set to gzip."""
        from app.core.config_production import CELERY_WORKER_CONFIG

        assert CELERY_WORKER_CONFIG["task_compression"] == "gzip"
        assert CELERY_WORKER_CONFIG["result_compression"] == "gzip"


class TestPerformanceThresholds:
    """Tests for PERFORMANCE_THRESHOLDS settings."""

    def test_thresholds_are_reasonable(self):
        """Test performance thresholds are set to reasonable values."""
        from app.core.config_production import PERFORMANCE_THRESHOLDS

        # Slow query should be at least 50ms
        assert PERFORMANCE_THRESHOLDS["slow_query_threshold_ms"] >= 50

        # Slow request should be at least 100ms
        assert PERFORMANCE_THRESHOLDS["slow_request_threshold_ms"] >= 100

        # Cache miss alert should be between 0 and 1
        assert 0 < PERFORMANCE_THRESHOLDS["cache_miss_alert_threshold"] < 1

        # DB connection alert should be between 0 and 1
        assert 0 < PERFORMANCE_THRESHOLDS["db_connection_alert_threshold"] < 1


class TestRequestConfig:
    """Tests for REQUEST_CONFIG settings."""

    def test_request_config_has_required_keys(self):
        """Test request config has essential settings."""
        from app.core.config_production import REQUEST_CONFIG

        required_keys = [
            "max_request_size",
            "request_timeout",
            "enable_request_id",
            "enable_correlation_id",
        ]

        for key in required_keys:
            assert key in REQUEST_CONFIG, f"Missing key: {key}"

    def test_max_request_size_reasonable(self):
        """Test max request size is reasonable (1-10 MB)."""
        from app.core.config_production import REQUEST_CONFIG

        # Between 1MB and 10MB
        assert 1_000_000 <= REQUEST_CONFIG["max_request_size"] <= 10_000_000


class TestStartupConfig:
    """Tests for STARTUP_CONFIG settings."""

    def test_startup_config_has_required_keys(self):
        """Test startup config has essential settings."""
        from app.core.config_production import STARTUP_CONFIG

        required_keys = [
            "lazy_apps",
            "preload_models",
            "warm_cache_on_startup",
            "check_migrations_on_startup",
        ]

        for key in required_keys:
            assert key in STARTUP_CONFIG, f"Missing key: {key}"


class TestGetProductionSettings:
    """Tests for get_production_settings function."""

    def test_returns_dict_with_all_sections(self):
        """Test get_production_settings returns complete config."""
        from app.core.config_production import get_production_settings

        settings = get_production_settings()

        expected_sections = [
            "database",
            "redis",
            "cache_ttl",
            "gunicorn",
            "celery",
            "performance",
            "request",
            "startup",
        ]

        for section in expected_sections:
            assert section in settings, f"Missing section: {section}"

    def test_database_section_is_pool_config(self):
        """Test database section contains pool config."""
        from app.core.config_production import DATABASE_POOL_CONFIG, get_production_settings

        settings = get_production_settings()

        assert settings["database"] == DATABASE_POOL_CONFIG


class TestCircuitBreakerConfig:
    """Tests for CIRCUIT_BREAKER_CONFIG settings."""

    def test_circuit_breaker_config_has_services(self):
        """Test circuit breaker config has expected services."""
        from app.core.config_production import CIRCUIT_BREAKER_CONFIG

        assert "database" in CIRCUIT_BREAKER_CONFIG
        assert "redis" in CIRCUIT_BREAKER_CONFIG
        assert "email" in CIRCUIT_BREAKER_CONFIG

    def test_circuit_breaker_has_required_settings(self):
        """Test each circuit breaker has required settings."""
        from app.core.config_production import CIRCUIT_BREAKER_CONFIG

        required_keys = ["failure_threshold", "recovery_timeout", "expected_exception"]

        for service, config in CIRCUIT_BREAKER_CONFIG.items():
            for key in required_keys:
                assert key in config, f"Missing {key} in {service} circuit breaker"


class TestMemoryConfig:
    """Tests for MEMORY_CONFIG settings."""

    def test_memory_config_has_required_keys(self):
        """Test memory config has essential settings."""
        from app.core.config_production import MEMORY_CONFIG

        required_keys = [
            "max_memory_percent",
            "gc_collect_interval",
            "clear_sqlalchemy_cache_interval",
        ]

        for key in required_keys:
            assert key in MEMORY_CONFIG, f"Missing key: {key}"

    def test_max_memory_percent_reasonable(self):
        """Test max memory percent is reasonable (50-95%)."""
        from app.core.config_production import MEMORY_CONFIG

        assert 50 <= MEMORY_CONFIG["max_memory_percent"] <= 95


class TestEnvironmentVariableOverrides:
    """Tests for environment variable override behavior."""

    def test_database_pool_size_override(self):
        """Test DATABASE_POOL_SIZE can be overridden."""
        with patch.dict(os.environ, {"DATABASE_POOL_SIZE": "10"}):
            import importlib

            import app.core.config_production as config_mod
            importlib.reload(config_mod)

            assert config_mod.DATABASE_POOL_CONFIG["pool_size"] == 10

    def test_gunicorn_workers_override(self):
        """Test GUNICORN_WORKERS can be overridden."""
        with patch.dict(os.environ, {"GUNICORN_WORKERS": "4"}):
            import importlib

            import app.core.config_production as config_mod
            importlib.reload(config_mod)

            assert config_mod.GUNICORN_CONFIG["workers"] == 4

    def test_celery_concurrency_override(self):
        """Test CELERY_WORKER_CONCURRENCY can be overridden."""
        with patch.dict(os.environ, {"CELERY_WORKER_CONCURRENCY": "8"}):
            import importlib

            import app.core.config_production as config_mod
            importlib.reload(config_mod)

            assert config_mod.CELERY_WORKER_CONFIG["concurrency"] == 8
