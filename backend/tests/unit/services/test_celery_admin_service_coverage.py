"""
Additional coverage tests for celery_admin_service.py — targeting missed lines:
  113->118, 133, 154->166, 282-284, 293->322, 304, 344->349, 468, 473->480,
  476-477, 488-489, 496-497, 506->513, 629, 638
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.services.celery_admin_service import CeleryAdminService


class TestGetWorkersOfflineBranch:
    """Cover the offline_workers increment (line 133) — though currently
    all Flower-returned workers count as online, this tests the summary logic."""

    @pytest.fixture
    def service(self, db):
        return CeleryAdminService(db)

    @pytest.mark.asyncio
    async def test_workers_empty_flower_response(self, service):
        """Lines 113->118: Flower returns empty dict → no workers, just summary."""
        with patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower:
            mock_flower.return_value = {}
            result = await service.get_workers()

        assert result["summary"]["total_workers"] == 0
        assert result["summary"]["online_workers"] == 0
        assert result["summary"]["offline_workers"] == 0
        assert result["workers"] == []

    @pytest.mark.asyncio
    async def test_workers_flower_unavailable(self, service):
        """Line 133 branch: Flower returns None (unreachable)."""
        with patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower:
            mock_flower.return_value = None
            result = await service.get_workers()

        assert result["summary"]["total_workers"] == 0
        assert result["workers"] == []

    @pytest.mark.asyncio
    async def test_workers_non_dict_pool_info(self, service):
        """Edge case: pool info is not a dict → concurrency defaults to 0."""
        mock_data = {
            "celery@worker1": {
                "active": [],
                "stats": {"total": {}, "pool": "not_a_dict"},
                "active_queues": [],
            },
        }
        with patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower:
            mock_flower.return_value = mock_data
            result = await service.get_workers()

        assert result["workers"][0]["concurrency"] == 0

    @pytest.mark.asyncio
    async def test_workers_non_list_active_queues(self, service):
        """Edge case: active_queues is not a list."""
        mock_data = {
            "celery@worker1": {
                "active": [],
                "stats": {"total": {}, "pool": {}},
                "active_queues": "not_a_list",
            },
        }
        with patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower:
            mock_flower.return_value = mock_data
            result = await service.get_workers()

        assert result["workers"][0]["queues"] == []


class TestGetQueuesEmptyBranch:
    """Cover lines 154->166: Flower returns None → no queues."""

    @pytest.fixture
    def service(self, db):
        return CeleryAdminService(db)

    @pytest.mark.asyncio
    async def test_queues_flower_unavailable(self, service):
        """Line 154->166: data is None → queues list stays empty."""
        with patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower:
            mock_flower.return_value = None
            result = await service.get_queues()

        assert result["queues"] == []
        assert result["total_depth"] == 0


class TestGetPaymentHealthDbFailure:
    """Cover lines 282-284: DB query exception in payment health."""

    @pytest.fixture
    def service(self, db):
        return CeleryAdminService(db)

    @pytest.mark.asyncio
    async def test_payment_health_db_exception(self, service):
        """Lines 282-284: _query_payment_health_counts raises → critical issue reported."""
        with (
            patch.object(
                service,
                "_query_payment_health_counts",
                side_effect=Exception("DB connection lost"),
            ),
            patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower,
        ):
            mock_flower.return_value = {}
            result = await service.get_payment_health()

        assert result["healthy"] is False
        assert any(i["severity"] == "critical" for i in result["issues"])
        assert any("DB query failed" in i["message"] for i in result["issues"])
        # Default counts should remain 0
        assert result["pending_authorizations"] == 0

    @pytest.mark.asyncio
    async def test_payment_health_pending_captures_over_threshold(self, service):
        """Line 304: pending_capture_count > 10 triggers warning."""
        mock_counts = {
            "pending_authorizations": 0,
            "overdue_authorizations": 0,
            "pending_captures": 15,
            "failed_payments_24h": 0,
        }
        with (
            patch.object(
                service,
                "_query_payment_health_counts",
                return_value=mock_counts,
            ),
            patch("asyncio.to_thread", return_value=mock_counts),
            patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower,
        ):
            mock_flower.return_value = {}
            result = await service.get_payment_health()

        assert result["pending_captures"] == 15
        assert any(
            "pending capture" in i["message"].lower()
            for i in result["issues"]
        )


class TestGetTaskHistoryTimestampBranches:
    """Cover lines 468, 473->480, 476-477, 488-489, 496-497, 506->513."""

    @pytest.fixture
    def service(self, db):
        return CeleryAdminService(db)

    @pytest.mark.asyncio
    async def test_task_history_invalid_received_timestamp(self, service):
        """Lines 473-477: invalid received timestamp → received_at is None,
        task NOT filtered (no received_at means it passes the cutoff check)."""
        mock_data = {
            "task-1": {
                "name": "test_task",
                "state": "SUCCESS",
                "received": "not_a_number",
                "started": None,
                "succeeded": None,
            },
        }
        with patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower:
            mock_flower.return_value = mock_data
            result = await service.get_task_history(hours=1)

        # With no valid received_at, the task passes the time filter
        assert result["count"] == 1
        assert result["tasks"][0]["received_at"] is None

    @pytest.mark.asyncio
    async def test_task_history_invalid_started_timestamp(self, service):
        """Lines 488-489: invalid started timestamp → started_at is None."""
        now = datetime.now(timezone.utc)
        mock_data = {
            "task-1": {
                "name": "test_task",
                "state": "STARTED",
                "received": (now - timedelta(minutes=5)).timestamp(),
                "started": "invalid",
            },
        }
        with patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower:
            mock_flower.return_value = mock_data
            result = await service.get_task_history(hours=1)

        assert result["tasks"][0]["started_at"] is None

    @pytest.mark.asyncio
    async def test_task_history_invalid_succeeded_timestamp(self, service):
        """Lines 496-497: invalid succeeded timestamp → succeeded_at is None."""
        now = datetime.now(timezone.utc)
        mock_data = {
            "task-1": {
                "name": "test_task",
                "state": "SUCCESS",
                "received": (now - timedelta(minutes=5)).timestamp(),
                "started": (now - timedelta(minutes=5)).timestamp(),
                "succeeded": "bad_timestamp",
            },
        }
        with patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower:
            mock_flower.return_value = mock_data
            result = await service.get_task_history(hours=1)

        assert result["tasks"][0]["succeeded_at"] is None
        assert result["tasks"][0]["runtime_seconds"] is None

    @pytest.mark.asyncio
    async def test_task_history_non_dict_task_info(self, service):
        """Line 468: non-dict task_info → skip."""
        now = datetime.now(timezone.utc)
        mock_data = {
            "task-1": "not_a_dict",
            "task-2": {
                "name": "real_task",
                "state": "SUCCESS",
                "received": (now - timedelta(minutes=2)).timestamp(),
            },
        }
        with patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower:
            mock_flower.return_value = mock_data
            result = await service.get_task_history(hours=1)

        assert result["count"] == 1
        assert result["tasks"][0]["task_name"] == "real_task"

    @pytest.mark.asyncio
    async def test_task_history_result_short_not_truncated(self, service):
        """Lines 506-511: short result is kept as-is, not truncated."""
        now = datetime.now(timezone.utc)
        mock_data = {
            "task-1": {
                "name": "test_task",
                "state": "SUCCESS",
                "received": (now - timedelta(minutes=5)).timestamp(),
                "result": "short result",
            },
        }
        with patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower:
            mock_flower.return_value = mock_data
            result = await service.get_task_history(hours=1)

        assert result["tasks"][0]["result"] == "short result"

    @pytest.mark.asyncio
    async def test_task_history_no_result(self, service):
        """Result is None/falsy → stays None."""
        now = datetime.now(timezone.utc)
        mock_data = {
            "task-1": {
                "name": "test_task",
                "state": "SUCCESS",
                "received": (now - timedelta(minutes=5)).timestamp(),
                "result": None,
            },
        }
        with patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower:
            mock_flower.return_value = mock_data
            result = await service.get_task_history(hours=1)

        assert result["tasks"][0]["result"] is None


class TestFormatScheduleAdditionalBranches:
    """Cover lines 629, 638 in _format_schedule."""

    def test_format_schedule_hourly_at_specific_minute(self):
        """Line 635: hourly at :XX."""
        from celery.schedules import crontab

        result = CeleryAdminService._format_schedule(crontab(minute="15", hour="*"))
        assert result == "hourly at :15"

    def test_format_schedule_crontab_fallback(self):
        """Line 638: fallback raw cron representation."""
        from celery.schedules import crontab

        # A crontab with wildcard minute and specific hour → doesn't match any pattern
        result = CeleryAdminService._format_schedule(crontab(minute="*", hour="3"))
        assert result.startswith("cron(")

    def test_format_schedule_day_of_month(self):
        """Line 629: specific time on a day of month."""
        from celery.schedules import crontab

        result = CeleryAdminService._format_schedule(
            crontab(minute="0", hour="3", day_of_month="15")
        )
        assert "day 15 of month" in result
        assert "03:00 UTC" in result

    def test_format_schedule_every_n_hours(self):
        """Line 610: every N hours via */N hour crontab."""
        from celery.schedules import crontab

        result = CeleryAdminService._format_schedule(crontab(hour="*/6"))
        assert result == "every 6 hours"


class TestGetPaymentHealthTaskHistoryBranches:
    """Cover lines 344->349 in get_payment_health: Flower task data edge cases."""

    @pytest.fixture
    def service(self, db):
        return CeleryAdminService(db)

    @pytest.mark.asyncio
    async def test_payment_health_task_no_received(self, service):
        """Lines 344-349: task_data exists but has no received timestamp."""
        task_data = {
            "task-123": {
                "name": "app.tasks.payment_tasks.process_scheduled_authorizations",
                "state": "SUCCESS",
                # No 'received' key
            },
        }
        mock_counts = {
            "pending_authorizations": 0,
            "overdue_authorizations": 0,
            "pending_captures": 0,
            "failed_payments_24h": 0,
        }
        with (
            patch.object(
                service,
                "_query_payment_health_counts",
                return_value=mock_counts,
            ),
            patch("asyncio.to_thread", return_value=mock_counts),
            patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower,
        ):
            mock_flower.return_value = task_data
            result = await service.get_payment_health()

        auth_task = next(
            t for t in result["last_task_runs"]
            if t["task_name"] == "process_scheduled_authorizations"
        )
        assert auth_task["last_run_at"] is None
        assert auth_task["status"] == "SUCCESS"

    @pytest.mark.asyncio
    async def test_payment_health_no_task_data(self, service):
        """Flower returns None for task queries → last_run_at is None."""
        mock_counts = {
            "pending_authorizations": 0,
            "overdue_authorizations": 0,
            "pending_captures": 0,
            "failed_payments_24h": 0,
        }
        with (
            patch.object(
                service,
                "_query_payment_health_counts",
                return_value=mock_counts,
            ),
            patch("asyncio.to_thread", return_value=mock_counts),
            patch.object(service, "_call_flower", new_callable=AsyncMock) as mock_flower,
        ):
            mock_flower.return_value = None
            result = await service.get_payment_health()

        for task in result["last_task_runs"]:
            assert task["last_run_at"] is None
            assert task["status"] is None
