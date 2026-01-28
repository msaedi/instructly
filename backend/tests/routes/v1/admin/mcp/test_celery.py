"""Tests for Celery MCP admin endpoints."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.models.booking import BookingStatus, PaymentStatus


class TestCeleryWorkersEndpoint:
    """Tests for GET /api/v1/admin/mcp/celery/workers"""

    def test_get_workers_success(self, client: TestClient, db, mcp_service_headers):
        """Test successful retrieval of worker status."""
        mock_flower_response = {
            "celery@worker1": {
                "status": True,
                "active": [{"id": "task-1"}],
                "stats": {"total": {"total": 100}},
                "concurrency": 4,
                "active_queues": [{"name": "celery"}, {"name": "default"}],
            },
            "celery@worker2": {
                "status": False,
                "active": [],
                "stats": {"total": {"total": 50}},
                "concurrency": 2,
                "active_queues": [{"name": "celery"}],
            },
        }

        with patch(
            "app.services.celery_admin_service.CeleryAdminService._call_flower",
            new_callable=AsyncMock,
            return_value=mock_flower_response,
        ):
            res = client.get(
                "/api/v1/admin/mcp/celery/workers",
                headers=mcp_service_headers,
            )

        assert res.status_code == 200
        data = res.json()

        assert "workers" in data
        assert "summary" in data
        assert "checked_at" in data

        assert len(data["workers"]) == 2
        assert data["summary"]["total_workers"] == 2
        assert data["summary"]["online_workers"] == 1
        assert data["summary"]["offline_workers"] == 1
        assert data["summary"]["total_active_tasks"] == 1

        # Check worker details
        worker1 = next(w for w in data["workers"] if w["hostname"] == "celery@worker1")
        assert worker1["status"] == "online"
        assert worker1["active_tasks"] == 1
        assert worker1["processed_total"] == 100
        assert worker1["concurrency"] == 4
        assert "celery" in worker1["queues"]

    def test_get_workers_flower_error(self, client: TestClient, db, mcp_service_headers):
        """Test graceful degradation when Flower is unavailable."""
        with patch(
            "app.services.celery_admin_service.CeleryAdminService._call_flower",
            new_callable=AsyncMock,
            return_value=None,  # Simulate Flower being unavailable
        ):
            res = client.get(
                "/api/v1/admin/mcp/celery/workers",
                headers=mcp_service_headers,
            )

        assert res.status_code == 200
        data = res.json()

        assert data["workers"] == []
        assert data["summary"]["total_workers"] == 0
        assert data["summary"]["online_workers"] == 0

    def test_get_workers_requires_auth(self, client: TestClient):
        """Test that endpoint requires authentication."""
        res = client.get("/api/v1/admin/mcp/celery/workers")
        assert res.status_code == 401


class TestCeleryQueuesEndpoint:
    """Tests for GET /api/v1/admin/mcp/celery/queues"""

    def test_get_queues_success(self, client: TestClient, db, mcp_service_headers):
        """Test successful retrieval of queue depths."""
        mock_flower_response = {
            "celery": 10,
            "default": 5,
            "priority": 0,
        }

        with patch(
            "app.services.celery_admin_service.CeleryAdminService._call_flower",
            new_callable=AsyncMock,
            return_value=mock_flower_response,
        ):
            res = client.get(
                "/api/v1/admin/mcp/celery/queues",
                headers=mcp_service_headers,
            )

        assert res.status_code == 200
        data = res.json()

        assert "queues" in data
        assert "total_depth" in data
        assert "checked_at" in data

        assert len(data["queues"]) == 3
        assert data["total_depth"] == 15

        celery_queue = next(q for q in data["queues"] if q["name"] == "celery")
        assert celery_queue["depth"] == 10


class TestCeleryFailedTasksEndpoint:
    """Tests for GET /api/v1/admin/mcp/celery/failed"""

    def test_get_failed_tasks_success(self, client: TestClient, db, mcp_service_headers):
        """Test successful retrieval of failed tasks."""
        mock_flower_response = {
            "task-id-1": {
                "name": "app.tasks.send_email",
                "state": "FAILURE",
                "queue": "celery",
                "received": 1704067200,  # 2024-01-01 00:00:00 UTC
                "exception": "ConnectionError('Failed to connect')",
                "traceback": "Traceback...",
                "args": "(1, 2, 3)",
                "kwargs": "{'key': 'value'}",
            },
            "task-id-2": {
                "name": "app.tasks.process_payment",
                "state": "FAILURE",
                "queue": "priority",
                "received": 1704153600,
                "exception": "ValueError('Invalid amount')",
                "traceback": "Traceback...",
                "args": "()",
                "kwargs": "{}",
            },
        }

        with patch(
            "app.services.celery_admin_service.CeleryAdminService._call_flower",
            new_callable=AsyncMock,
            return_value=mock_flower_response,
        ):
            res = client.get(
                "/api/v1/admin/mcp/celery/failed",
                headers=mcp_service_headers,
            )

        assert res.status_code == 200
        data = res.json()

        assert "failed_tasks" in data
        assert "count" in data
        assert "checked_at" in data

        assert data["count"] == 2
        assert len(data["failed_tasks"]) == 2

        task1 = next(t for t in data["failed_tasks"] if t["task_id"] == "task-id-1")
        assert task1["task_name"] == "app.tasks.send_email"
        assert task1["queue"] == "celery"
        assert "ConnectionError" in task1["exception"]

    def test_get_failed_tasks_empty(self, client: TestClient, db, mcp_service_headers):
        """Test when there are no failed tasks."""
        with patch(
            "app.services.celery_admin_service.CeleryAdminService._call_flower",
            new_callable=AsyncMock,
            return_value={},
        ):
            res = client.get(
                "/api/v1/admin/mcp/celery/failed",
                headers=mcp_service_headers,
            )

        assert res.status_code == 200
        data = res.json()

        assert data["count"] == 0
        assert data["failed_tasks"] == []

    def test_get_failed_tasks_limit_capped(self, client: TestClient, db, mcp_service_headers):
        """Test that limit parameter is capped at 100."""
        with patch(
            "app.services.celery_admin_service.CeleryAdminService._call_flower",
            new_callable=AsyncMock,
            return_value={},
        ):
            res = client.get(
                "/api/v1/admin/mcp/celery/failed?limit=200",
                headers=mcp_service_headers,
            )

        # FastAPI validates limit <= 100, so this should return 422
        assert res.status_code == 422

    def test_get_failed_tasks_valid_limit(self, client: TestClient, db, mcp_service_headers):
        """Test that valid limit works."""
        with patch(
            "app.services.celery_admin_service.CeleryAdminService._call_flower",
            new_callable=AsyncMock,
            return_value={},
        ):
            res = client.get(
                "/api/v1/admin/mcp/celery/failed?limit=25",
                headers=mcp_service_headers,
            )

        assert res.status_code == 200


class TestCeleryPaymentHealthEndpoint:
    """Tests for GET /api/v1/admin/mcp/celery/payment-health"""

    def test_get_payment_health_healthy(
        self,
        client: TestClient,
        db,
        mcp_service_headers,
    ):
        """Test healthy payment pipeline status."""
        with patch(
            "app.services.celery_admin_service.CeleryAdminService._call_flower",
            new_callable=AsyncMock,
            return_value={},
        ):
            res = client.get(
                "/api/v1/admin/mcp/celery/payment-health",
                headers=mcp_service_headers,
            )

        assert res.status_code == 200
        data = res.json()

        assert "healthy" in data
        assert "issues" in data
        assert "pending_authorizations" in data
        assert "overdue_authorizations" in data
        assert "pending_captures" in data
        assert "failed_payments_24h" in data
        assert "last_task_runs" in data
        assert "checked_at" in data

    def test_get_payment_health_with_issues(
        self,
        client: TestClient,
        db,
        test_booking,
        mcp_service_headers,
    ):
        """Test payment health with issues detected."""
        # Update the existing test_booking to have an overdue scheduled payment
        now = datetime.now(timezone.utc)
        test_booking.payment_status = PaymentStatus.SCHEDULED.value
        test_booking.status = BookingStatus.CONFIRMED.value
        test_booking.booking_start_utc = now + timedelta(hours=12)  # Within 24h
        test_booking.booking_end_utc = now + timedelta(hours=13)
        test_booking.booking_date = (now + timedelta(hours=12)).date()
        db.commit()

        with patch(
            "app.services.celery_admin_service.CeleryAdminService._call_flower",
            new_callable=AsyncMock,
            return_value={},
        ):
            res = client.get(
                "/api/v1/admin/mcp/celery/payment-health",
                headers=mcp_service_headers,
            )

        assert res.status_code == 200
        data = res.json()

        # Should detect the overdue authorization
        assert data["overdue_authorizations"] >= 1

    def test_endpoints_require_mcp_auth(self, client: TestClient):
        """Test that all endpoints require MCP authentication."""
        endpoints = [
            "/api/v1/admin/mcp/celery/workers",
            "/api/v1/admin/mcp/celery/queues",
            "/api/v1/admin/mcp/celery/failed",
            "/api/v1/admin/mcp/celery/payment-health",
        ]

        for endpoint in endpoints:
            res = client.get(endpoint)
            assert res.status_code == 401, f"Endpoint {endpoint} should require auth"

    def test_endpoints_reject_invalid_token(self, client: TestClient):
        """Test that all endpoints reject invalid tokens."""
        endpoints = [
            "/api/v1/admin/mcp/celery/workers",
            "/api/v1/admin/mcp/celery/queues",
            "/api/v1/admin/mcp/celery/failed",
            "/api/v1/admin/mcp/celery/payment-health",
        ]

        for endpoint in endpoints:
            res = client.get(
                endpoint,
                headers={"Authorization": "Bearer invalid-token"},
            )
            assert res.status_code == 401, f"Endpoint {endpoint} should reject invalid token"
