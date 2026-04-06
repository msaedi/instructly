"""Unit tests for core/lifespan.py — startup/shutdown helper functions."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.lifespan import (
    _clear_cache_event_loop_reference,
    _close_redis_clients,
    _connect_sse_broadcast,
    _disconnect_sse_broadcast,
    _initialize_observability,
    _initialize_production_startup,
    _initialize_search_cache,
    _log_pytest_mode,
    _log_startup_banner,
    _set_cache_event_loop,
    _shutdown_background_job_worker,
    _start_background_job_worker,
    _validate_startup_config,
)

# ---------------------------------------------------------------------------
# _validate_startup_config
# ---------------------------------------------------------------------------


class TestValidateStartupConfig:
    @patch("app.core.lifespan.secret_or_plain", return_value="")
    def test_prod_mode_validates_encryption(self, mock_secret: MagicMock) -> None:
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.site_mode = "prod"
            mock_settings.bgc_encryption_key = "test-key"
            mock_settings.hundredms_enabled = False
            with patch("app.core.crypto.validate_bgc_encryption_key"):
                _validate_startup_config()

    @patch("app.core.lifespan.secret_or_plain", return_value="some-key")
    def test_non_prod_with_key_logs(self, mock_secret: MagicMock) -> None:
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.site_mode = "dev"
            mock_settings.hundredms_enabled = False
            mock_settings.bgc_encryption_key = "some-key"
            _validate_startup_config()

    @patch("app.core.lifespan.secret_or_plain", return_value="")
    def test_hundredms_enabled_missing_keys_raises(self, mock_secret: MagicMock) -> None:
        with patch("app.core.config.settings") as mock_settings:
            mock_settings.site_mode = "dev"
            mock_settings.hundredms_enabled = True
            mock_settings.hundredms_access_key = None
            mock_settings.hundredms_app_secret = None
            mock_settings.hundredms_template_id = None
            mock_settings.hundredms_webhook_secret = None
            mock_settings.bgc_encryption_key = None

            with pytest.raises(ValueError, match="HUNDREDMS_ENABLED=True"):
                _validate_startup_config()


# ---------------------------------------------------------------------------
# _log_startup_banner
# ---------------------------------------------------------------------------


class TestLogStartupBanner:
    def test_production_mode(self) -> None:
        with patch("app.core.lifespan.settings") as mock_settings:
            mock_settings.environment = "production"
            app = MagicMock()
            _log_startup_banner(app)

    def test_development_mode(self) -> None:
        with patch("app.core.lifespan.settings") as mock_settings:
            mock_settings.environment = "development"
            app = MagicMock()
            _log_startup_banner(app)


# ---------------------------------------------------------------------------
# _initialize_observability
# ---------------------------------------------------------------------------


class TestInitializeObservability:
    @patch("app.core.lifespan.instrument_additional_libraries")
    @patch("app.core.lifespan.instrument_fastapi")
    @patch("app.core.lifespan.init_otel", return_value=False)
    def test_init_otel_returns_false(self, mock_init: MagicMock, mock_inst: MagicMock, mock_add: MagicMock) -> None:
        _initialize_observability(MagicMock())
        mock_inst.assert_not_called()

    @patch("app.core.lifespan.instrument_additional_libraries")
    @patch("app.core.lifespan.instrument_fastapi")
    @patch("app.core.lifespan.init_otel", return_value=True)
    def test_init_otel_returns_true(self, mock_init: MagicMock, mock_inst: MagicMock, mock_add: MagicMock) -> None:
        app = MagicMock()
        _initialize_observability(app)
        mock_inst.assert_called_once_with(app)
        mock_add.assert_called_once()

    @patch("app.core.lifespan.init_otel", side_effect=Exception("otel crash"))
    def test_otel_exception_caught(self, mock_init: MagicMock) -> None:
        _initialize_observability(MagicMock())  # should not raise


# ---------------------------------------------------------------------------
# _set_cache_event_loop / _clear_cache_event_loop_reference
# ---------------------------------------------------------------------------


class TestCacheEventLoop:
    def test_set_cache_exception_caught(self) -> None:
        with patch("app.core.lifespan.asyncio.get_running_loop", side_effect=RuntimeError("no loop")):
            with patch.dict("sys.modules", {"app.services.cache_service": MagicMock()}):
                _set_cache_event_loop()

    def test_clear_cache_exception_caught(self) -> None:
        with patch.dict("sys.modules", {"app.services.cache_service": MagicMock(side_effect=Exception)}):
            _clear_cache_event_loop_reference()  # should not raise


# ---------------------------------------------------------------------------
# _log_pytest_mode
# ---------------------------------------------------------------------------


class TestLogPytestMode:
    def test_running_tests_true(self) -> None:
        with patch("app.core.config.is_running_tests", return_value=True):
            _log_pytest_mode()

    def test_running_tests_false(self) -> None:
        with patch("app.core.config.is_running_tests", return_value=False):
            _log_pytest_mode()

    def test_detection_exception(self) -> None:
        with patch("app.core.config.is_running_tests", side_effect=Exception("fail")):
            _log_pytest_mode()  # should not raise


# ---------------------------------------------------------------------------
# _initialize_production_startup
# ---------------------------------------------------------------------------


class TestInitializeProductionStartup:
    @pytest.mark.asyncio
    async def test_non_production_returns_early(self) -> None:
        with patch("app.core.lifespan.settings") as mock_settings:
            mock_settings.environment = "development"
            await _initialize_production_startup()

    @pytest.mark.asyncio
    async def test_production_calls_initialize(self) -> None:
        with patch("app.core.lifespan.settings") as mock_settings:
            mock_settings.environment = "production"
            with patch("app.core.production_startup.ProductionStartup.initialize", new_callable=AsyncMock) as mock_init:
                await _initialize_production_startup()
                mock_init.assert_called_once()


# ---------------------------------------------------------------------------
# _initialize_search_cache
# ---------------------------------------------------------------------------


class TestInitializeSearchCache:
    def test_exception_caught(self) -> None:
        with patch("app.core.lifespan._initialize_search_cache") as mock_fn:
            mock_fn.side_effect = None
            _initialize_search_cache()

    def test_import_failure_caught(self) -> None:
        with patch.dict("sys.modules", {"app.services.cache_service": None}):
            _initialize_search_cache()  # should not raise


# ---------------------------------------------------------------------------
# SSE broadcast connect/disconnect
# ---------------------------------------------------------------------------


class TestSSEBroadcast:
    @pytest.mark.asyncio
    async def test_connect_success(self) -> None:
        with patch("app.core.lifespan.connect_broadcast", new_callable=AsyncMock):
            await _connect_sse_broadcast()

    @pytest.mark.asyncio
    async def test_connect_exception(self) -> None:
        with patch("app.core.lifespan.connect_broadcast", new_callable=AsyncMock, side_effect=Exception("fail")):
            await _connect_sse_broadcast()

    @pytest.mark.asyncio
    async def test_disconnect_success(self) -> None:
        with patch("app.core.lifespan.disconnect_broadcast", new_callable=AsyncMock):
            await _disconnect_sse_broadcast()

    @pytest.mark.asyncio
    async def test_disconnect_exception(self) -> None:
        with patch("app.core.lifespan.disconnect_broadcast", new_callable=AsyncMock, side_effect=Exception("fail")):
            await _disconnect_sse_broadcast()


# ---------------------------------------------------------------------------
# _close_redis_clients
# ---------------------------------------------------------------------------


class TestCloseRedisClients:
    @pytest.mark.asyncio
    async def test_all_close_successfully(self) -> None:
        with patch("app.core.lifespan.close_async_redis_client", new_callable=AsyncMock):
            with patch("app.core.cache_redis.close_async_cache_redis_client", new_callable=AsyncMock):
                with patch("app.ratelimit.redis_backend.close_async_rate_limit_redis_client", new_callable=AsyncMock):
                    await _close_redis_clients()

    @pytest.mark.asyncio
    async def test_all_close_with_exceptions(self) -> None:
        with patch("app.core.lifespan.close_async_redis_client", new_callable=AsyncMock, side_effect=Exception("fail")):
            await _close_redis_clients()  # should not raise


# ---------------------------------------------------------------------------
# _start_background_job_worker / _shutdown_background_job_worker
# ---------------------------------------------------------------------------


class TestBackgroundJobWorker:
    def test_disabled_in_testing_mode(self) -> None:
        with patch("app.core.lifespan.settings") as mock_settings:
            mock_settings.bgc_expiry_enabled = False
            mock_settings.scheduler_enabled = True
            mock_settings.is_testing = True
            task, stop = _start_background_job_worker()
            assert task is None
            assert stop is None

    def test_disabled_scheduler(self) -> None:
        with patch("app.core.lifespan.settings") as mock_settings:
            mock_settings.bgc_expiry_enabled = False
            mock_settings.scheduler_enabled = False
            mock_settings.is_testing = False
            task, stop = _start_background_job_worker()
            assert task is None

    @pytest.mark.asyncio
    async def test_shutdown_none_task(self) -> None:
        await _shutdown_background_job_worker(None, None)

    @pytest.mark.asyncio
    async def test_shutdown_with_task(self) -> None:
        import threading

        stop = threading.Event()
        task = AsyncMock()
        task.__await__ = lambda self: iter([None])
        # Use a real completed future
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        future.set_result(None)
        await _shutdown_background_job_worker(future, stop)
        assert stop.is_set()
