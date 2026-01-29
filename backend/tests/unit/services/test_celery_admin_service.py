"""Unit tests for CeleryAdminService."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.models.booking import BookingStatus, PaymentStatus
from app.services.celery_admin_service import CeleryAdminService, _secret_value


class TestSecretValueHelper:
    """Tests for _secret_value helper function."""

    def test_secret_value_none(self):
        """Test _secret_value returns empty string for None."""
        assert _secret_value(None) == ""

    def test_secret_value_with_get_secret_value(self):
        """Test _secret_value calls get_secret_value if available."""
        mock_secret = MagicMock()
        mock_secret.get_secret_value.return_value = "secret123"
        assert _secret_value(mock_secret) == "secret123"

    def test_secret_value_plain_string(self):
        """Test _secret_value returns string for plain value."""
        assert _secret_value("plaintext") == "plaintext"

    def test_secret_value_non_callable_attribute(self):
        """Test _secret_value handles non-callable get_secret_value."""
        mock_obj = MagicMock()
        mock_obj.get_secret_value = "not_callable"
        assert _secret_value(mock_obj) == str(mock_obj)


class TestCallFlower:
    """Tests for _call_flower method."""

    @pytest.fixture
    def service(self, db):
        """Create CeleryAdminService instance."""
        return CeleryAdminService(db)

    @pytest.mark.asyncio
    async def test_call_flower_success(self, service):
        """Test successful Flower API call."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"workers": []}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.request.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await service._call_flower("/api/workers")

        assert result == {"workers": []}
        mock_instance.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_call_flower_with_auth(self, service):
        """Test Flower API call with authentication."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": "test"}
        mock_response.raise_for_status = MagicMock()

        with (
            patch("httpx.AsyncClient") as mock_client,
            patch("app.services.celery_admin_service.settings") as mock_settings,
        ):
            mock_settings.flower_url = "http://flower:5555"
            mock_settings.flower_user = "admin"
            mock_settings.flower_password = MagicMock()
            mock_settings.flower_password.get_secret_value.return_value = "password123"

            mock_instance = AsyncMock()
            mock_instance.request.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await service._call_flower("/api/workers")

        assert result == {"data": "test"}
        # Verify auth was passed
        call_kwargs = mock_instance.request.call_args
        assert call_kwargs.kwargs.get("auth") is not None

    @pytest.mark.asyncio
    async def test_call_flower_timeout(self, service):
        """Test Flower API timeout returns None."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.request.side_effect = httpx.TimeoutException("timeout")
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await service._call_flower("/api/workers")

        assert result is None

    @pytest.mark.asyncio
    async def test_call_flower_http_error(self, service):
        """Test Flower API HTTP error returns None."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.request.side_effect = httpx.HTTPStatusError(
                "500 error",
                request=MagicMock(),
                response=MagicMock(),
            )
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await service._call_flower("/api/workers")

        assert result is None

    @pytest.mark.asyncio
    async def test_call_flower_unexpected_error(self, service):
        """Test Flower API unexpected error returns None."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.request.side_effect = Exception("unexpected error")
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await service._call_flower("/api/workers")

        assert result is None

    @pytest.mark.asyncio
    async def test_call_flower_custom_timeout(self, service):
        """Test Flower API call with custom timeout."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": "test"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.request.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await service._call_flower("/api/workers", timeout=30.0)

        assert result == {"data": "test"}
        # Verify custom timeout was used
        mock_client.assert_called_with(timeout=30.0)

    @pytest.mark.asyncio
    async def test_call_flower_with_params(self, service):
        """Test Flower API call with query parameters."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"tasks": []}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.request.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await service._call_flower(
                "/api/tasks",
                params={"state": "FAILURE", "limit": 10},
            )

        assert result == {"tasks": []}
        call_kwargs = mock_instance.request.call_args
        assert call_kwargs.kwargs.get("params") == {"state": "FAILURE", "limit": 10}


class TestGetWorkersEdgeCases:
    """Edge case tests for get_workers method."""

    @pytest.fixture
    def service(self, db):
        """Create CeleryAdminService instance."""
        return CeleryAdminService(db)

    @pytest.mark.asyncio
    async def test_get_workers_with_non_list_active(self, service):
        """Test workers with non-list active tasks."""
        mock_data = {
            "celery@worker1": {
                "status": True,
                "active": "not_a_list",  # Edge case: not a list
                "stats": {"total": {"total": 10}},
                "concurrency": 2,
                "active_queues": [],
            },
        }

        with patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower:
            mock_flower.return_value = mock_data
            result = await service.get_workers()

        assert result["workers"][0]["active_tasks"] == 0

    @pytest.mark.asyncio
    async def test_get_workers_with_non_dict_stats(self, service):
        """Test workers with non-dict stats."""
        mock_data = {
            "celery@worker1": {
                "status": True,
                "active": [],
                "stats": {"total": "not_a_dict"},  # Edge case
                "concurrency": 2,
                "active_queues": [],
            },
        }

        with patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower:
            mock_flower.return_value = mock_data
            result = await service.get_workers()

        assert result["workers"][0]["processed_total"] == 0

    @pytest.mark.asyncio
    async def test_get_workers_with_invalid_queue_entries(self, service):
        """Test workers with invalid queue entries."""
        mock_data = {
            "celery@worker1": {
                "status": True,
                "active": [],
                "stats": {},
                "concurrency": 2,
                "active_queues": [
                    {"name": "valid_queue"},
                    "not_a_dict",
                    {"no_name_key": True},
                ],
            },
        }

        with patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower:
            mock_flower.return_value = mock_data
            result = await service.get_workers()

        assert result["workers"][0]["queues"] == ["valid_queue"]


class TestGetQueuesEdgeCases:
    """Edge case tests for get_queues method."""

    @pytest.fixture
    def service(self, db):
        """Create CeleryAdminService instance."""
        return CeleryAdminService(db)

    @pytest.mark.asyncio
    async def test_get_queues_with_non_int_depth(self, service):
        """Test queues with non-integer depth values."""
        mock_data = {
            "celery": "not_an_int",
            "default": 5,
        }

        with patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower:
            mock_flower.return_value = mock_data
            result = await service.get_queues()

        celery_queue = next(q for q in result["queues"] if q["name"] == "celery")
        assert celery_queue["depth"] == 0
        assert result["total_depth"] == 5


class TestGetFailedTasksEdgeCases:
    """Edge case tests for get_failed_tasks method."""

    @pytest.fixture
    def service(self, db):
        """Create CeleryAdminService instance."""
        return CeleryAdminService(db)

    @pytest.mark.asyncio
    async def test_get_failed_tasks_with_non_dict_task(self, service):
        """Test handling of non-dict task info."""
        mock_data = {
            "task-1": "not_a_dict",
            "task-2": {
                "name": "valid_task",
                "received": 1704067200,
            },
        }

        with patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower:
            mock_flower.return_value = mock_data
            result = await service.get_failed_tasks()

        assert result["count"] == 1
        assert result["failed_tasks"][0]["task_name"] == "valid_task"

    @pytest.mark.asyncio
    async def test_get_failed_tasks_with_invalid_timestamp(self, service):
        """Test handling of invalid received timestamp."""
        mock_data = {
            "task-1": {
                "name": "test_task",
                "received": "invalid_timestamp",
            },
        }

        with patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower:
            mock_flower.return_value = mock_data
            result = await service.get_failed_tasks()

        assert result["failed_tasks"][0]["failed_at"] is None

    @pytest.mark.asyncio
    async def test_get_failed_tasks_truncates_long_traceback(self, service):
        """Test that long tracebacks are truncated."""
        long_traceback = "x" * 2000
        mock_data = {
            "task-1": {
                "name": "test_task",
                "traceback": long_traceback,
            },
        }

        with patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower:
            mock_flower.return_value = mock_data
            result = await service.get_failed_tasks()

        assert len(result["failed_tasks"][0]["traceback"]) == 1003  # 1000 + "..."

    @pytest.mark.asyncio
    async def test_get_failed_tasks_truncates_long_args(self, service):
        """Test that long args are truncated."""
        long_args = "(" + "x" * 300 + ")"
        long_kwargs = "{" + "x" * 300 + "}"
        mock_data = {
            "task-1": {
                "name": "test_task",
                "args": long_args,
                "kwargs": long_kwargs,
            },
        }

        with patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower:
            mock_flower.return_value = mock_data
            result = await service.get_failed_tasks()

        assert len(result["failed_tasks"][0]["task_args"]) == 203  # 200 + "..."
        assert len(result["failed_tasks"][0]["task_kwargs"]) == 203


class TestGetPaymentHealthWithTaskHistory:
    """Tests for get_payment_health with Flower task history."""

    @pytest.fixture
    def service(self, db):
        """Create CeleryAdminService instance."""
        return CeleryAdminService(db)

    @pytest.mark.asyncio
    async def test_get_payment_health_with_task_runs(self, service):
        """Test payment health with task run history from Flower."""
        task_data = {
            "task-123": {
                "name": "app.tasks.payment_tasks.process_scheduled_authorizations",
                "state": "SUCCESS",
                "received": 1704067200,
            },
        }

        with patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower:
            # Return task data for task queries, empty for others
            mock_flower.return_value = task_data
            result = await service.get_payment_health()

        # Should have last_task_runs populated
        assert len(result["last_task_runs"]) == 3
        # Check that at least one has data
        auth_task = next(
            t for t in result["last_task_runs"]
            if t["task_name"] == "process_scheduled_authorizations"
        )
        assert auth_task["status"] == "SUCCESS"
        assert auth_task["last_run_at"] is not None

    @pytest.mark.asyncio
    async def test_get_payment_health_with_invalid_task_timestamp(self, service):
        """Test payment health handles invalid task timestamps."""
        task_data = {
            "task-123": {
                "name": "app.tasks.payment_tasks.capture_completed_lessons",
                "state": "SUCCESS",
                "received": "invalid",
            },
        }

        with patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower:
            mock_flower.return_value = task_data
            result = await service.get_payment_health()

        capture_task = next(
            t for t in result["last_task_runs"]
            if t["task_name"] == "capture_completed_lessons"
        )
        assert capture_task["last_run_at"] is None
        assert capture_task["status"] == "SUCCESS"

    @pytest.mark.asyncio
    async def test_get_payment_health_with_non_dict_task_info(self, service):
        """Test payment health handles non-dict task info."""
        task_data = {
            "task-123": "not_a_dict",
        }

        with patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower:
            mock_flower.return_value = task_data
            result = await service.get_payment_health()

        # Should still complete without error
        assert "last_task_runs" in result

    @pytest.mark.asyncio
    async def test_get_payment_health_critical_issues(self, service, db, test_booking):
        """Test payment health detects critical issues."""
        # Set up a booking with overdue authorization
        now = datetime.now(timezone.utc)
        test_booking.payment_status = PaymentStatus.SCHEDULED.value
        test_booking.status = BookingStatus.CONFIRMED.value
        test_booking.booking_start_utc = now + timedelta(hours=12)
        test_booking.booking_end_utc = now + timedelta(hours=13)
        test_booking.booking_date = (now + timedelta(hours=12)).date()
        db.commit()

        with patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower:
            mock_flower.return_value = {}
            result = await service.get_payment_health()

        assert result["healthy"] is False
        assert result["overdue_authorizations"] >= 1
        assert any(i["severity"] == "critical" for i in result["issues"])

    @pytest.mark.asyncio
    async def test_get_payment_health_warning_for_pending_captures(
        self, service, db, test_booking
    ):
        """Test payment health warns about high pending captures."""
        test_booking.payment_status = PaymentStatus.AUTHORIZED.value
        test_booking.status = BookingStatus.COMPLETED.value
        db.commit()

        with patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower:
            mock_flower.return_value = {}
            result = await service.get_payment_health()

        # With just one booking, should not trigger warning (threshold is >10)
        assert result["pending_captures"] >= 1

    @pytest.mark.asyncio
    async def test_get_payment_health_warning_for_failed_payments(
        self, service, db, test_booking
    ):
        """Test payment health warns about failed payments in last 24h."""
        now = datetime.now(timezone.utc)
        test_booking.payment_status = PaymentStatus.PAYMENT_METHOD_REQUIRED.value
        test_booking.updated_at = now - timedelta(hours=1)
        db.commit()

        with patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower:
            mock_flower.return_value = {}
            result = await service.get_payment_health()

        assert result["failed_payments_24h"] >= 1
        assert any(
            i["message"] == "Failed payments in last 24 hours" for i in result["issues"]
        )


# ==================== TIER 2: Active Tasks, Task History, Beat Schedule ====================


class TestGetActiveTasks:
    """Tests for get_active_tasks method."""

    @pytest.fixture
    def service(self, db):
        """Create CeleryAdminService instance."""
        return CeleryAdminService(db)

    @pytest.mark.asyncio
    async def test_get_active_tasks_success(self, service):
        """Test successful retrieval of active tasks."""
        mock_data = {
            "task-1": {
                "name": "app.tasks.send_email",
                "worker": "celery@worker1",
                "started": 1704067200,
                "args": "(1, 2)",
                "kwargs": "{'key': 'value'}",
            },
            "task-2": {
                "name": "app.tasks.process_payment",
                "worker": "celery@worker2",
                "started": 1704067300,
            },
        }

        with patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower:
            mock_flower.return_value = mock_data
            result = await service.get_active_tasks()

        assert result["count"] == 2
        assert len(result["tasks"]) == 2
        assert result["tasks"][0]["task_id"] == "task-1"
        assert result["tasks"][0]["task_name"] == "app.tasks.send_email"
        assert result["tasks"][0]["worker"] == "celery@worker1"
        assert result["tasks"][0]["started_at"] is not None
        assert "checked_at" in result

    @pytest.mark.asyncio
    async def test_get_active_tasks_empty(self, service):
        """Test empty active tasks response."""
        with patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower:
            mock_flower.return_value = {}
            result = await service.get_active_tasks()

        assert result["count"] == 0
        assert result["tasks"] == []

    @pytest.mark.asyncio
    async def test_get_active_tasks_flower_unavailable(self, service):
        """Test graceful handling when Flower is unavailable."""
        with patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower:
            mock_flower.return_value = None
            result = await service.get_active_tasks()

        assert result["count"] == 0
        assert result["tasks"] == []

    @pytest.mark.asyncio
    async def test_get_active_tasks_non_dict_task(self, service):
        """Test handling of non-dict task info."""
        mock_data = {
            "task-1": "not_a_dict",
            "task-2": {
                "name": "valid_task",
                "worker": "worker1",
            },
        }

        with patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower:
            mock_flower.return_value = mock_data
            result = await service.get_active_tasks()

        assert result["count"] == 1
        assert result["tasks"][0]["task_name"] == "valid_task"

    @pytest.mark.asyncio
    async def test_get_active_tasks_invalid_timestamp(self, service):
        """Test handling of invalid started timestamp."""
        mock_data = {
            "task-1": {
                "name": "test_task",
                "worker": "worker1",
                "started": "invalid",
            },
        }

        with patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower:
            mock_flower.return_value = mock_data
            result = await service.get_active_tasks()

        assert result["tasks"][0]["started_at"] is None

    @pytest.mark.asyncio
    async def test_get_active_tasks_truncates_long_args(self, service):
        """Test that long args are truncated."""
        long_args = "(" + "x" * 300 + ")"
        mock_data = {
            "task-1": {
                "name": "test_task",
                "worker": "worker1",
                "args": long_args,
            },
        }

        with patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower:
            mock_flower.return_value = mock_data
            result = await service.get_active_tasks()

        assert len(result["tasks"][0]["args"]) == 203  # 200 + "..."


class TestGetTaskHistory:
    """Tests for get_task_history method."""

    @pytest.fixture
    def service(self, db):
        """Create CeleryAdminService instance."""
        return CeleryAdminService(db)

    @pytest.mark.asyncio
    async def test_get_task_history_success(self, service):
        """Test successful retrieval of task history."""
        now = datetime.now(timezone.utc)
        started_ts = (now - timedelta(minutes=10)).timestamp()
        succeeded_ts = (now - timedelta(minutes=9)).timestamp()

        mock_data = {
            "task-1": {
                "name": "app.tasks.send_email",
                "state": "SUCCESS",
                "received": started_ts - 10,
                "started": started_ts,
                "succeeded": succeeded_ts,
                "result": "Email sent",
                "retries": 0,
            },
        }

        with patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower:
            mock_flower.return_value = mock_data
            result = await service.get_task_history(hours=1, limit=100)

        assert result["count"] == 1
        assert result["tasks"][0]["task_name"] == "app.tasks.send_email"
        assert result["tasks"][0]["state"] == "SUCCESS"
        assert result["tasks"][0]["runtime_seconds"] is not None
        assert result["filters_applied"]["hours"] == 1
        assert result["filters_applied"]["limit"] == 100

    @pytest.mark.asyncio
    async def test_get_task_history_with_filters(self, service):
        """Test task history with filters applied."""
        mock_data = {}

        with patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower:
            mock_flower.return_value = mock_data
            result = await service.get_task_history(
                task_name="send_email",
                state="FAILURE",
                hours=12,
                limit=50,
            )

        assert result["filters_applied"]["task_name"] == "send_email"
        assert result["filters_applied"]["state"] == "FAILURE"
        assert result["filters_applied"]["hours"] == 12
        assert result["filters_applied"]["limit"] == 50

    @pytest.mark.asyncio
    async def test_get_task_history_caps_parameters(self, service):
        """Test that hours and limit are capped to max values."""
        mock_data = {}

        with patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower:
            mock_flower.return_value = mock_data
            result = await service.get_task_history(hours=100, limit=1000)

        # Should be capped to max values
        assert result["filters_applied"]["hours"] == 24
        assert result["filters_applied"]["limit"] == 500

    @pytest.mark.asyncio
    async def test_get_task_history_filters_by_time(self, service):
        """Test that tasks outside time window are filtered out."""
        now = datetime.now(timezone.utc)
        old_timestamp = (now - timedelta(hours=5)).timestamp()

        mock_data = {
            "task-1": {
                "name": "old_task",
                "state": "SUCCESS",
                "received": old_timestamp,
            },
        }

        with patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower:
            mock_flower.return_value = mock_data
            result = await service.get_task_history(hours=1)

        # Task from 5 hours ago should be filtered out when looking back 1 hour
        assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_get_task_history_truncates_long_result(self, service):
        """Test that long results are truncated."""
        now = datetime.now(timezone.utc)
        long_result = "x" * 1000
        mock_data = {
            "task-1": {
                "name": "test_task",
                "state": "SUCCESS",
                "received": (now - timedelta(minutes=5)).timestamp(),
                "result": long_result,
            },
        }

        with patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower:
            mock_flower.return_value = mock_data
            result = await service.get_task_history(hours=1)

        assert len(result["tasks"][0]["result"]) == 503  # 500 + "..."

    @pytest.mark.asyncio
    async def test_get_task_history_empty(self, service):
        """Test empty task history response."""
        with patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower:
            mock_flower.return_value = None
            result = await service.get_task_history()

        assert result["count"] == 0
        assert result["tasks"] == []


class TestGetBeatSchedule:
    """Tests for get_beat_schedule method."""

    @pytest.fixture
    def service(self, db):
        """Create CeleryAdminService instance."""
        return CeleryAdminService(db)

    @pytest.mark.asyncio
    async def test_get_beat_schedule_success(self, service):
        """Test successful retrieval of beat schedule."""
        result = await service.get_beat_schedule()

        assert "tasks" in result
        assert "count" in result
        assert "checked_at" in result
        assert result["count"] > 0
        assert len(result["tasks"]) == result["count"]

        # Each task should have the expected fields
        for task in result["tasks"]:
            assert "name" in task
            assert "task" in task
            assert "schedule" in task
            assert "enabled" in task

    @pytest.mark.asyncio
    async def test_get_beat_schedule_contains_known_tasks(self, service):
        """Test that beat schedule contains expected tasks."""
        result = await service.get_beat_schedule()

        task_names = [t["name"] for t in result["tasks"]]

        # Check for some expected tasks from beat_schedule.py
        assert "notifications-dispatch-pending" in task_names
        assert "calculate-service-analytics" in task_names

    @pytest.mark.asyncio
    async def test_get_beat_schedule_human_readable_schedules(self, service):
        """Test that schedules are human-readable."""
        result = await service.get_beat_schedule()

        # Find a task with timedelta schedule (dispatch-pending runs every 30 seconds)
        dispatch_task = next(
            (t for t in result["tasks"] if t["name"] == "notifications-dispatch-pending"),
            None,
        )
        if dispatch_task:
            assert "second" in dispatch_task["schedule"].lower()

        # Find a task with crontab schedule
        analytics_task = next(
            (t for t in result["tasks"] if t["name"] == "calculate-service-analytics"),
            None,
        )
        if analytics_task:
            # Should be "03:30 UTC" or similar
            assert "utc" in analytics_task["schedule"].lower() or ":" in analytics_task["schedule"]


class TestFormatSchedule:
    """Tests for _format_schedule static method."""

    def test_format_schedule_timedelta_seconds(self):
        """Test formatting timedelta in seconds."""
        result = CeleryAdminService._format_schedule(timedelta(seconds=30))
        assert result == "every 30 seconds"

    def test_format_schedule_timedelta_minutes(self):
        """Test formatting timedelta in minutes."""
        result = CeleryAdminService._format_schedule(timedelta(minutes=5))
        assert result == "every 5 minutes"

        result = CeleryAdminService._format_schedule(timedelta(minutes=1))
        assert result == "every 1 minute"

    def test_format_schedule_timedelta_hours(self):
        """Test formatting timedelta in hours."""
        result = CeleryAdminService._format_schedule(timedelta(hours=2))
        assert result == "every 2 hours"

        result = CeleryAdminService._format_schedule(timedelta(hours=1))
        assert result == "every 1 hour"

    def test_format_schedule_crontab_every_n_minutes(self):
        """Test formatting crontab with */N minutes."""
        from celery.schedules import crontab
        result = CeleryAdminService._format_schedule(crontab(minute="*/15"))
        assert result == "every 15 minutes"

    def test_format_schedule_crontab_specific_time(self):
        """Test formatting crontab with specific time."""
        from celery.schedules import crontab
        result = CeleryAdminService._format_schedule(crontab(hour=3, minute=30))
        assert "03:30 UTC" in result

    def test_format_schedule_crontab_day_of_week(self):
        """Test formatting crontab with day of week."""
        from celery.schedules import crontab
        result = CeleryAdminService._format_schedule(crontab(day_of_week=0, hour=1, minute=0))
        assert "Sunday" in result
        assert "01:00 UTC" in result

    def test_format_schedule_unknown_type(self):
        """Test formatting unknown schedule type."""
        result = CeleryAdminService._format_schedule("unknown")
        assert result == "unknown"
