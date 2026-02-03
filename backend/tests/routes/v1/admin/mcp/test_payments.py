"""Tests for payment timeline MCP endpoint."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


class TestPaymentTimelineEndpoint:
    def test_payment_timeline_requires_scope(self, client: TestClient):
        res = client.get("/api/v1/admin/mcp/payments/timeline")
        assert res.status_code == 401

    def test_payment_timeline_requires_identifier(self, client: TestClient, mcp_service_headers):
        res = client.get(
            "/api/v1/admin/mcp/payments/timeline",
            headers=mcp_service_headers,
        )
        assert res.status_code == 422

        res = client.get(
            "/api/v1/admin/mcp/payments/timeline?booking_id=01TEST&user_id=01USER",
            headers=mcp_service_headers,
        )
        assert res.status_code == 422

    def test_payment_timeline_returns_time_window(self, client: TestClient, mcp_service_headers):
        mock_result = {
            "payments": [
                {
                    "booking_id": "01BOOK",
                    "created_at": datetime(2026, 2, 1, tzinfo=timezone.utc),
                    "amount": {
                        "gross": 90.0,
                        "platform_fee": 10.8,
                        "credits_applied": 0.0,
                        "tip": 0.0,
                        "net_to_instructor": 79.2,
                    },
                    "status": "settled",
                    "status_timeline": [
                        {"ts": datetime(2026, 2, 1, tzinfo=timezone.utc), "state": "captured"}
                    ],
                    "scheduled_capture_at": None,
                    "provider_refs": {"payment_intent": "pi_...1234"},
                    "failure": None,
                    "refunds": [],
                }
            ],
            "summary": {"by_status": {"settled": 1}},
            "flags": {
                "has_failed_payment": False,
                "has_pending_refund": False,
                "possible_double_charge": False,
            },
            "total_count": 1,
        }

        with patch(
            "app.services.admin_ops_service.AdminOpsService.get_payment_timeline",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            res = client.get(
                "/api/v1/admin/mcp/payments/timeline"
                "?booking_id=01BOOK"
                "&start_time=2026-02-01T00:00:00Z"
                "&end_time=2026-02-02T00:00:00Z",
                headers=mcp_service_headers,
            )

        assert res.status_code == 200
        data = res.json()
        assert data["meta"]["time_window"]["start"].startswith("2026-02-01")
        assert data["meta"]["time_window"]["end"].startswith("2026-02-02")
        assert data["meta"]["total_count"] == 1

    def test_payment_timeline_since_hours_uses_default_window(
        self, client: TestClient, mcp_service_headers
    ):
        mock_result = {
            "payments": [],
            "summary": {"by_status": {}},
            "flags": {
                "has_failed_payment": False,
                "has_pending_refund": False,
                "possible_double_charge": False,
            },
            "total_count": 0,
        }

        with patch(
            "app.services.admin_ops_service.AdminOpsService.get_payment_timeline",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            res = client.get(
                "/api/v1/admin/mcp/payments/timeline?booking_id=01BOOK&since_hours=48",
                headers=mcp_service_headers,
            )

        assert res.status_code == 200
        payload = res.json()
        assert payload["meta"]["time_window"]["source"] == "since_hours=48"

    def test_payment_timeline_start_time_only_uses_now(
        self, client: TestClient, mcp_service_headers
    ):
        mock_result = {
            "payments": [],
            "summary": {"by_status": {}},
            "flags": {
                "has_failed_payment": False,
                "has_pending_refund": False,
                "possible_double_charge": False,
            },
            "total_count": 0,
        }

        with patch(
            "app.services.admin_ops_service.AdminOpsService.get_payment_timeline",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            res = client.get(
                "/api/v1/admin/mcp/payments/timeline?booking_id=01BOOK&start_time=2026-02-01T00:00:00",
                headers=mcp_service_headers,
            )

        assert res.status_code == 200
        payload = res.json()
        assert payload["meta"]["time_window"]["start"].startswith("2026-02-01T00:00:00")
        assert payload["meta"]["time_window"]["source"].endswith("end_time=now")

    def test_payment_timeline_end_time_without_start_time_rejected(
        self, client: TestClient, mcp_service_headers
    ):
        res = client.get(
            "/api/v1/admin/mcp/payments/timeline?booking_id=01BOOK&end_time=2026-02-02T00:00:00Z",
            headers=mcp_service_headers,
        )

        assert res.status_code == 422

    def test_payment_timeline_start_after_end_rejected(
        self, client: TestClient, mcp_service_headers
    ):
        res = client.get(
            "/api/v1/admin/mcp/payments/timeline"
            "?booking_id=01BOOK"
            "&start_time=2026-02-03T00:00:00Z"
            "&end_time=2026-02-02T00:00:00Z",
            headers=mcp_service_headers,
        )

        assert res.status_code == 422
