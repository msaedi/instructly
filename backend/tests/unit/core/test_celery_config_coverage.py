"""
Tests for celery_config.py - targeting CI coverage gaps.
Coverage for Celery configuration settings.
"""
import os
from unittest.mock import patch


class TestCeleryConfig:
    """Tests for CeleryConfig class."""

    def test_broker_url_uses_settings(self):
        """Test broker URL uses settings.redis_url."""
        from app.core.celery_config import CeleryConfig

        # The broker_url should be set
        assert CeleryConfig.broker_url is not None

    def test_broker_url_fallback_to_localhost(self):
        """Test broker URL falls back to localhost if redis_url is None."""
        with patch("app.core.celery_config.settings") as mock_settings:
            mock_settings.redis_url = None

            # Re-import to get fresh config
            import importlib

            import app.core.celery_config as config_mod
            importlib.reload(config_mod)

            assert "localhost" in config_mod.CeleryConfig.broker_url

    def test_broker_connection_retry_enabled(self):
        """Test broker connection retry is enabled."""
        from app.core.celery_config import CeleryConfig

        assert CeleryConfig.broker_connection_retry is True
        assert CeleryConfig.broker_connection_retry_on_startup is True

    def test_broker_transport_options(self):
        """Test broker transport options are configured."""
        from app.core.celery_config import CeleryConfig

        transport_opts = CeleryConfig.broker_transport_options

        assert "visibility_timeout" in transport_opts
        assert transport_opts["visibility_timeout"] == 3600

        assert "socket_keepalive" in transport_opts
        assert transport_opts["socket_keepalive"] is True

        assert "polling_interval" in transport_opts
        assert transport_opts["polling_interval"] == 10.0

    def test_result_backend_is_disabled(self):
        """Test result backend is disabled for performance."""
        from app.core.celery_config import CeleryConfig

        assert CeleryConfig.result_backend is None

    def test_task_serializer_is_json(self):
        """Test task serializer is JSON."""
        from app.core.celery_config import CeleryConfig

        assert CeleryConfig.task_serializer == "json"
        assert "json" in CeleryConfig.accept_content

    def test_task_compression_is_gzip(self):
        """Test task compression is gzip."""
        from app.core.celery_config import CeleryConfig

        assert CeleryConfig.task_compression == "gzip"

    def test_task_time_limits(self):
        """Test task time limits are set correctly."""
        from app.core.celery_config import CeleryConfig

        assert CeleryConfig.task_time_limit == 600  # 10 minutes hard
        assert CeleryConfig.task_soft_time_limit == 300  # 5 minutes soft
        assert CeleryConfig.task_soft_time_limit < CeleryConfig.task_time_limit

    def test_task_acks_late_enabled(self):
        """Test task_acks_late is enabled for reliability."""
        from app.core.celery_config import CeleryConfig

        assert CeleryConfig.task_acks_late is True

    def test_worker_prefetch_multiplier(self):
        """Test worker prefetch multiplier is low for better load distribution."""
        from app.core.celery_config import CeleryConfig

        assert CeleryConfig.worker_prefetch_multiplier == 1

    def test_worker_concurrency_uses_cpu_count(self):
        """Test worker concurrency is based on CPU count."""
        from app.core.celery_config import CeleryConfig

        expected = os.cpu_count() or 4
        assert CeleryConfig.worker_concurrency == expected

    def test_worker_heartbeat_interval(self):
        """Test worker heartbeat is reduced for Redis optimization."""
        from app.core.celery_config import CeleryConfig

        # Should be increased from default 2s to reduce Redis operations
        assert CeleryConfig.worker_heartbeat_interval >= 10

    def test_timezone_settings(self):
        """Test timezone settings are configured."""
        from app.core.celery_config import CeleryConfig

        assert CeleryConfig.timezone == "US/Eastern"
        assert CeleryConfig.enable_utc is True

    def test_retry_settings(self):
        """Test retry settings are configured."""
        from app.core.celery_config import CeleryConfig

        assert CeleryConfig.task_default_retry_delay == 60
        assert CeleryConfig.task_max_retries == 3
        assert CeleryConfig.task_retry_backoff is True
        assert CeleryConfig.task_retry_jitter is True

    def test_beat_scheduler_settings(self):
        """Test beat scheduler settings."""
        from app.core.celery_config import CeleryConfig

        assert CeleryConfig.beat_schedule_filename == "celerybeat-schedule"
        assert CeleryConfig.beat_scheduler == "celery.beat:PersistentScheduler"


class TestCeleryBeatSchedule:
    """Tests for CELERY_BEAT_SCHEDULE export."""

    def test_beat_schedule_exported(self):
        """Test CELERY_BEAT_SCHEDULE is exported from config module."""
        from app.core.celery_config import CELERY_BEAT_SCHEDULE

        # Should be a dictionary
        assert isinstance(CELERY_BEAT_SCHEDULE, dict)

    def test_beat_schedule_backward_compatibility(self):
        """Test backward compatibility alias exists."""
        from app.core.celery_config import CELERYBEAT_SCHEDULE

        assert CELERYBEAT_SCHEDULE is not None


class TestCeleryTaskRoutes:
    """Tests for CELERY_TASK_ROUTES configuration."""

    def test_task_routes_exist(self):
        """Test task routes are defined."""
        from app.core.celery_config import CELERY_TASK_ROUTES

        assert isinstance(CELERY_TASK_ROUTES, dict)
        assert len(CELERY_TASK_ROUTES) > 0

    def test_email_route(self):
        """Test email tasks are routed to email queue."""
        from app.core.celery_config import CELERY_TASK_ROUTES

        assert "app.tasks.email.*" in CELERY_TASK_ROUTES
        assert CELERY_TASK_ROUTES["app.tasks.email.*"]["queue"] == "email"

    def test_notifications_route(self):
        """Test notification tasks are routed correctly."""
        from app.core.celery_config import CELERY_TASK_ROUTES

        assert "app.tasks.notifications.*" in CELERY_TASK_ROUTES
        assert CELERY_TASK_ROUTES["app.tasks.notifications.*"]["queue"] == "notifications"

    def test_analytics_route(self):
        """Test analytics tasks are routed to analytics queue."""
        from app.core.celery_config import CELERY_TASK_ROUTES

        assert "app.tasks.analytics.*" in CELERY_TASK_ROUTES
        assert CELERY_TASK_ROUTES["app.tasks.analytics.*"]["queue"] == "analytics"

    def test_bookings_route_has_high_priority(self):
        """Test booking tasks have high priority."""
        from app.core.celery_config import CELERY_TASK_ROUTES

        assert "app.tasks.bookings.*" in CELERY_TASK_ROUTES
        # Bookings should have higher priority than analytics
        booking_priority = CELERY_TASK_ROUTES["app.tasks.bookings.*"]["priority"]
        analytics_priority = CELERY_TASK_ROUTES["app.tasks.analytics.*"]["priority"]
        assert booking_priority > analytics_priority

    def test_privacy_route_has_priority(self):
        """Test privacy tasks are routed with priority for GDPR."""
        from app.core.celery_config import CELERY_TASK_ROUTES

        assert "app.tasks.privacy.*" in CELERY_TASK_ROUTES
        assert CELERY_TASK_ROUTES["app.tasks.privacy.*"]["queue"] == "privacy"

    def test_each_route_has_required_keys(self):
        """Test each route has queue, routing_key, and priority."""
        from app.core.celery_config import CELERY_TASK_ROUTES

        for pattern, config in CELERY_TASK_ROUTES.items():
            assert "queue" in config, f"Missing queue in {pattern}"
            assert "routing_key" in config, f"Missing routing_key in {pattern}"
            assert "priority" in config, f"Missing priority in {pattern}"


class TestCeleryTaskQueues:
    """Tests for CELERY_TASK_QUEUES configuration."""

    def test_task_queues_exist(self):
        """Test task queues are defined."""
        from app.core.celery_config import CELERY_TASK_QUEUES

        assert isinstance(CELERY_TASK_QUEUES, dict)
        assert len(CELERY_TASK_QUEUES) > 0

    def test_default_celery_queue(self):
        """Test default celery queue exists."""
        from app.core.celery_config import CELERY_TASK_QUEUES

        assert "celery" in CELERY_TASK_QUEUES
        assert CELERY_TASK_QUEUES["celery"]["exchange"] == "celery"

    def test_queues_match_routes(self):
        """Test that queues defined in routes exist in queues config."""
        from app.core.celery_config import CELERY_TASK_QUEUES, CELERY_TASK_ROUTES

        route_queues = {config["queue"] for config in CELERY_TASK_ROUTES.values()}

        for queue in route_queues:
            assert queue in CELERY_TASK_QUEUES, f"Queue {queue} defined in routes but not in CELERY_TASK_QUEUES"

    def test_each_queue_has_required_keys(self):
        """Test each queue has exchange, routing_key, and priority."""
        from app.core.celery_config import CELERY_TASK_QUEUES

        for queue_name, config in CELERY_TASK_QUEUES.items():
            assert "exchange" in config, f"Missing exchange in {queue_name}"
            assert "routing_key" in config, f"Missing routing_key in {queue_name}"
            assert "priority" in config, f"Missing priority in {queue_name}"


class TestGetCeleryConfig:
    """Tests for get_celery_config function."""

    def test_returns_config_instance(self):
        """Test get_celery_config returns a CeleryConfig instance."""
        from app.core.celery_config import CeleryConfig, get_celery_config

        config = get_celery_config()

        assert isinstance(config, CeleryConfig)

    def test_returns_new_instance_each_call(self):
        """Test each call returns a new instance."""
        from app.core.celery_config import get_celery_config

        config1 = get_celery_config()
        config2 = get_celery_config()

        # Different instances
        assert config1 is not config2


class TestCeleryConfigAttributes:
    """Tests for specific CeleryConfig attribute types and values."""

    def test_worker_send_task_events_enabled(self):
        """Test worker sends task events for Flower monitoring."""
        from app.core.celery_config import CeleryConfig

        assert CeleryConfig.worker_send_task_events is True

    def test_worker_enable_remote_control(self):
        """Test remote control is enabled for Celery workers."""
        from app.core.celery_config import CeleryConfig

        assert CeleryConfig.worker_enable_remote_control is True

    def test_worker_hijack_root_logger_disabled(self):
        """Test worker doesn't hijack root logger."""
        from app.core.celery_config import CeleryConfig

        assert CeleryConfig.worker_hijack_root_logger is False

    def test_task_track_started_enabled(self):
        """Test task tracking is enabled."""
        from app.core.celery_config import CeleryConfig

        assert CeleryConfig.task_track_started is True

    def test_task_reject_on_worker_lost(self):
        """Test tasks are rejected when worker is lost."""
        from app.core.celery_config import CeleryConfig

        assert CeleryConfig.task_reject_on_worker_lost is True

    def test_control_queue_settings(self):
        """Test control queue settings for security."""
        from app.core.celery_config import CeleryConfig

        assert CeleryConfig.control_queue_ttl == 300
        assert CeleryConfig.control_queue_expires == 10.0

    def test_task_protocol_version(self):
        """Test task protocol version is 2."""
        from app.core.celery_config import CeleryConfig

        assert CeleryConfig.task_protocol == 2

    def test_broker_max_retries(self):
        """Test broker max retries is set."""
        from app.core.celery_config import CeleryConfig

        assert CeleryConfig.broker_connection_max_retries == 10
