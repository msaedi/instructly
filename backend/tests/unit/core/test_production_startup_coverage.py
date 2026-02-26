"""
Tests for production_startup.py - targeting CI coverage gaps.
Bug hunting + coverage for production initialization code.

BUGS FOUND:
1. Line 168: Unsafe dict access summary['memory']['rss_mb'] - could KeyError
2. Lines 133-140: Potential resource leak if exception during connection warming
"""
import logging
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.production_startup import ProductionStartup


class TestProductionStartup:
    """Tests for ProductionStartup class."""

    @pytest.mark.asyncio
    async def test_initialize_skips_non_production(self):
        """Test that initialization is skipped when not in production."""
        with patch("app.core.production_startup.settings") as mock_settings:
            mock_settings.environment = "development"

            # Should not raise, just skip
            await ProductionStartup.initialize()

    @pytest.mark.asyncio
    async def test_initialize_runs_in_production(self):
        """Test full initialization in production mode."""
        with patch("app.core.production_startup.settings") as mock_settings, \
             patch.object(ProductionStartup, "_configure_logging") as mock_logging, \
             patch.object(ProductionStartup, "_verify_services", new_callable=AsyncMock) as mock_verify, \
             patch.object(ProductionStartup, "_setup_monitoring", new_callable=AsyncMock) as mock_monitor:
            mock_settings.environment = "production"

            await ProductionStartup.initialize()

            mock_logging.assert_called_once()
            mock_verify.assert_called_once()
            mock_monitor.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_warms_connections_when_enabled(self):
        """Test connection warming when WARM_CONNECTIONS=true."""
        with patch("app.core.production_startup.settings") as mock_settings, \
             patch.dict(os.environ, {"WARM_CONNECTIONS": "true"}), \
             patch.object(ProductionStartup, "_configure_logging"), \
             patch.object(ProductionStartup, "_verify_services", new_callable=AsyncMock), \
             patch.object(ProductionStartup, "_warm_connections", new_callable=AsyncMock) as mock_warm, \
             patch.object(ProductionStartup, "_setup_monitoring", new_callable=AsyncMock):
            mock_settings.environment = "production"

            await ProductionStartup.initialize()

            mock_warm.assert_called_once()


class TestConfigureLogging:
    """Tests for _configure_logging method."""

    def test_configure_logging_sets_log_levels(self):
        """Test that logging levels are properly configured."""
        with patch.dict(os.environ, {"STRUCTURED_LOGS": "false"}):
            from app.core.production_startup import ProductionStartup

            ProductionStartup._configure_logging()

            # Verify log levels were set
            assert logging.getLogger("sqlalchemy.engine").level == logging.WARNING
            assert logging.getLogger("sqlalchemy.pool").level == logging.INFO
            assert logging.getLogger("urllib3").level == logging.WARNING
            assert logging.getLogger("asyncio").level == logging.WARNING

    def test_configure_logging_with_structured_logs(self):
        """Test structured logging configuration."""
        with patch.dict(os.environ, {"STRUCTURED_LOGS": "true"}):
            from app.core.production_startup import ProductionStartup

            ProductionStartup._configure_logging()

            # Verify a handler was added to root logger
            assert len(logging.root.handlers) > 0

    def test_structured_formatter_format(self):
        """Test the StructuredFormatter output format."""
        with patch.dict(os.environ, {"STRUCTURED_LOGS": "true"}):
            import json

            from app.core.production_startup import ProductionStartup

            ProductionStartup._configure_logging()

            # The handler should be a StructuredFormatter
            handler = logging.root.handlers[0]
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="",
                lineno=0,
                msg="test message",
                args=(),
                exc_info=None,
            )

            formatted = handler.formatter.format(record)
            parsed = json.loads(formatted)

            assert parsed["level"] == "INFO"
            assert parsed["message"] == "test message"
            assert parsed["logger"] == "test"
            assert "timestamp" in parsed


class TestVerifyServices:
    """Tests for _verify_services method."""

    @pytest.mark.asyncio
    async def test_verify_services_database_success(self):
        """Test database verification success path."""
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        mock_redis_client = AsyncMock()

        with patch("app.database.engine", mock_engine), \
             patch("app.core.cache_redis.get_async_cache_redis_client", new_callable=AsyncMock) as mock_redis:
            mock_redis.return_value = mock_redis_client

            await ProductionStartup._verify_services()
            # Should not raise

    @pytest.mark.asyncio
    async def test_verify_services_database_failure_non_strict(self):
        """Test database failure in non-strict mode logs error but continues."""
        mock_engine = MagicMock()
        mock_engine.connect.side_effect = Exception("Database unavailable")

        mock_redis_client = AsyncMock()

        with patch.dict(os.environ, {"STRICT_STARTUP": "false"}), \
             patch("app.database.engine", mock_engine), \
             patch("app.core.cache_redis.get_async_cache_redis_client", new_callable=AsyncMock) as mock_redis:
            mock_redis.return_value = mock_redis_client

            # Should not raise in non-strict mode
            await ProductionStartup._verify_services()

    @pytest.mark.asyncio
    async def test_verify_services_database_failure_strict(self):
        """Test database failure in strict mode raises exception."""
        mock_engine = MagicMock()
        mock_engine.connect.side_effect = Exception("Database unavailable")

        with patch.dict(os.environ, {"STRICT_STARTUP": "true"}), \
             patch("app.database.engine", mock_engine):

            with pytest.raises(Exception, match="Database unavailable"):
                await ProductionStartup._verify_services()

    @pytest.mark.asyncio
    async def test_verify_services_redis_unavailable(self):
        """Test Redis unavailable returns None and logs warning."""
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        with patch("app.database.engine", mock_engine), \
             patch("app.core.cache_redis.get_async_cache_redis_client", new_callable=AsyncMock) as mock_redis:
            mock_redis.return_value = None  # Redis unavailable

            # Should not raise, function catches RuntimeError internally
            await ProductionStartup._verify_services()

    @pytest.mark.asyncio
    async def test_verify_services_redis_ping_fails(self):
        """Test Redis ping failure logs warning."""
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        mock_redis_client = AsyncMock()
        mock_redis_client.ping.side_effect = Exception("Connection refused")

        with patch("app.database.engine", mock_engine), \
             patch("app.core.cache_redis.get_async_cache_redis_client", new_callable=AsyncMock) as mock_redis:
            mock_redis.return_value = mock_redis_client

            # Should not raise, just log warning
            await ProductionStartup._verify_services()


class TestWarmConnections:
    """Tests for _warm_connections method."""

    @pytest.mark.asyncio
    async def test_warm_connections_success(self):
        """Test successful connection warming."""
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value = mock_conn

        with patch.dict(os.environ, {"DATABASE_POOL_SIZE": "5"}), \
             patch("app.database.engine", mock_engine):

            await ProductionStartup._warm_connections()

            # Should create min(pool_size, 3) = 3 connections
            assert mock_engine.connect.call_count == 3
            assert mock_conn.close.call_count == 3

    @pytest.mark.asyncio
    async def test_warm_connections_with_small_pool(self):
        """Test warming with pool size smaller than 3."""
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value = mock_conn

        with patch.dict(os.environ, {"DATABASE_POOL_SIZE": "2"}), \
             patch("app.database.engine", mock_engine):

            await ProductionStartup._warm_connections()

            # Should create min(2, 3) = 2 connections
            assert mock_engine.connect.call_count == 2

    @pytest.mark.asyncio
    async def test_warm_connections_failure_logs_warning(self):
        """Test that connection warming failure logs warning but doesn't raise."""
        mock_engine = MagicMock()
        mock_engine.connect.side_effect = Exception("Connection failed")

        with patch("app.database.engine", mock_engine):

            # Should not raise, just log warning
            await ProductionStartup._warm_connections()

    @pytest.mark.asyncio
    async def test_warm_connections_cleans_up_on_execute_failure(self):
        """
        REGRESSION TEST: Verify resource leak fix.
        If execute() fails after connect(), connection should still be closed.
        """
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value = mock_conn
        # First execute succeeds, second fails
        mock_conn.execute.side_effect = [None, Exception("Execute failed")]

        with patch.dict(os.environ, {"DATABASE_POOL_SIZE": "5"}), \
             patch("app.database.engine", mock_engine):

            await ProductionStartup._warm_connections()

            # Should have tried to create 2 connections (2nd failed on execute)
            assert mock_engine.connect.call_count == 2
            # Both connections should be closed (finally block cleanup)
            assert mock_conn.close.call_count == 2


class TestSetupMonitoring:
    """Tests for _setup_monitoring method."""

    @pytest.mark.asyncio
    async def test_setup_monitoring_skips_in_testing_mode(self):
        """Test monitoring setup is skipped in testing mode."""
        with patch("app.core.production_startup.settings") as mock_settings:
            mock_settings.is_testing = True
            mock_settings.scheduler_enabled = True

            await ProductionStartup._setup_monitoring()
            # Should not raise or start background task

    @pytest.mark.asyncio
    async def test_setup_monitoring_skips_when_scheduler_disabled(self):
        """Test monitoring setup is skipped when scheduler is disabled."""
        with patch("app.core.production_startup.settings") as mock_settings:
            mock_settings.is_testing = False
            mock_settings.scheduler_enabled = False

            await ProductionStartup._setup_monitoring()
            # Should not raise or start background task

    @pytest.mark.asyncio
    async def test_setup_monitoring_starts_background_task(self):
        """Test monitoring starts background task when enabled."""
        mock_monitor = MagicMock()
        mock_monitor.get_performance_summary.return_value = {
            "memory": {"rss_mb": 100}
        }

        async def mock_health_check():
            pass

        with patch("app.core.production_startup.settings") as mock_settings, \
             patch("app.monitoring.production_monitor.periodic_health_check", mock_health_check), \
             patch("app.monitoring.production_monitor.monitor", mock_monitor):
            mock_settings.is_testing = False
            mock_settings.scheduler_enabled = True

            await ProductionStartup._setup_monitoring()
            # The background task is created via asyncio.create_task

    @pytest.mark.asyncio
    async def test_setup_monitoring_handles_missing_memory_key(self):
        """
        REGRESSION TEST: Verify fix for unsafe dict access.
        Previously summary['memory']['rss_mb'] would raise KeyError.
        Now uses .get() with defaults.
        """
        mock_monitor = MagicMock()
        # Return incomplete data - missing 'memory' key
        mock_monitor.get_performance_summary.return_value = {}

        async def mock_health_check():
            pass

        with patch("app.core.production_startup.settings") as mock_settings, \
             patch("app.monitoring.production_monitor.periodic_health_check", mock_health_check), \
             patch("app.monitoring.production_monitor.monitor", mock_monitor):
            mock_settings.is_testing = False
            mock_settings.scheduler_enabled = True

            # Should NOT raise KeyError - fix uses .get() with defaults
            await ProductionStartup._setup_monitoring()
            # Verify the function completed without error
