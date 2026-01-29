"""Tests for Admin Operations MCP endpoints."""

from unittest.mock import patch

from fastapi.testclient import TestClient


class TestBookingSummaryEndpoint:
    """Tests for GET /api/v1/admin/mcp/ops/bookings/summary"""

    def test_get_booking_summary_success(self, client: TestClient, db, mcp_service_headers):
        """Test successful retrieval of booking summary."""
        mock_summary = {
            "total_bookings": 10,
            "by_status": {"CONFIRMED": 5, "COMPLETED": 3, "CANCELLED": 2},
            "total_revenue_cents": 100000,
            "avg_booking_value_cents": 10000,
            "new_students": 3,
            "repeat_students": 5,
            "top_categories": [{"category": "Music", "count": 5}],
        }

        with patch(
            "app.services.admin_ops_service.AdminOpsService._query_booking_summary",
            return_value=mock_summary,
        ):
            res = client.get(
                "/api/v1/admin/mcp/ops/bookings/summary?period=today",
                headers=mcp_service_headers,
            )

        assert res.status_code == 200
        data = res.json()

        assert "summary" in data
        assert "checked_at" in data
        assert data["summary"]["period"] == "today"
        assert data["summary"]["total_bookings"] == 10
        assert data["summary"]["total_revenue_cents"] == 100000

    def test_get_booking_summary_different_periods(
        self, client: TestClient, db, mcp_service_headers
    ):
        """Test different period parameters."""
        periods = ["today", "yesterday", "this_week", "last_7_days", "this_month"]

        for period in periods:
            with patch(
                "app.services.admin_ops_service.AdminOpsService._query_booking_summary",
                return_value={
                    "total_bookings": 0,
                    "by_status": {},
                    "total_revenue_cents": 0,
                    "avg_booking_value_cents": 0,
                    "new_students": 0,
                    "repeat_students": 0,
                    "top_categories": [],
                },
            ):
                res = client.get(
                    f"/api/v1/admin/mcp/ops/bookings/summary?period={period}",
                    headers=mcp_service_headers,
                )

            assert res.status_code == 200
            assert res.json()["summary"]["period"] == period

    def test_get_booking_summary_requires_auth(self, client: TestClient):
        """Test that endpoint requires authentication."""
        res = client.get("/api/v1/admin/mcp/ops/bookings/summary")
        assert res.status_code == 401


class TestRecentBookingsEndpoint:
    """Tests for GET /api/v1/admin/mcp/ops/bookings/recent"""

    def test_get_recent_bookings_success(self, client: TestClient, db, mcp_service_headers):
        """Test successful retrieval of recent bookings."""
        mock_bookings = [
            {
                "booking_id": "01K2TEST123456789012345",
                "status": "CONFIRMED",
                "booking_date": "2024-01-15",
                "start_time": "10:00:00",
                "end_time": "11:00:00",
                "student_name": "John S.",
                "instructor_name": "Sarah C.",
                "service_name": "Piano Lesson",
                "category": "Music",
                "total_cents": 10000,
                "location_type": "STUDENT_LOCATION",
                "created_at": "2024-01-15T09:00:00Z",
            }
        ]

        with patch(
            "app.services.admin_ops_service.AdminOpsService._query_recent_bookings",
            return_value=mock_bookings,
        ):
            res = client.get(
                "/api/v1/admin/mcp/ops/bookings/recent",
                headers=mcp_service_headers,
            )

        assert res.status_code == 200
        data = res.json()

        assert "bookings" in data
        assert "count" in data
        assert "filters_applied" in data
        assert "checked_at" in data

        assert data["count"] == 1
        assert data["bookings"][0]["student_name"] == "John S."

    def test_get_recent_bookings_with_filters(
        self, client: TestClient, db, mcp_service_headers
    ):
        """Test recent bookings with filters."""
        with patch(
            "app.services.admin_ops_service.AdminOpsService._query_recent_bookings",
            return_value=[],
        ):
            res = client.get(
                "/api/v1/admin/mcp/ops/bookings/recent?status=confirmed&limit=50&hours=48",
                headers=mcp_service_headers,
            )

        assert res.status_code == 200
        data = res.json()

        assert data["filters_applied"]["status"] == "confirmed"
        assert data["filters_applied"]["limit"] == 50
        assert data["filters_applied"]["hours"] == 48

    def test_get_recent_bookings_invalid_limit(
        self, client: TestClient, db, mcp_service_headers
    ):
        """Test that limit parameter is validated."""
        res = client.get(
            "/api/v1/admin/mcp/ops/bookings/recent?limit=500",
            headers=mcp_service_headers,
        )

        # FastAPI validates limit <= 100, so this should return 422
        assert res.status_code == 422

    def test_get_recent_bookings_invalid_hours(
        self, client: TestClient, db, mcp_service_headers
    ):
        """Test that hours parameter is validated."""
        res = client.get(
            "/api/v1/admin/mcp/ops/bookings/recent?hours=500",
            headers=mcp_service_headers,
        )

        # FastAPI validates hours <= 168, so this should return 422
        assert res.status_code == 422

    def test_get_recent_bookings_requires_auth(self, client: TestClient):
        """Test that endpoint requires authentication."""
        res = client.get("/api/v1/admin/mcp/ops/bookings/recent")
        assert res.status_code == 401


class TestPaymentPipelineEndpoint:
    """Tests for GET /api/v1/admin/mcp/ops/payments/pipeline"""

    def test_get_payment_pipeline_success(
        self, client: TestClient, db, mcp_service_headers
    ):
        """Test successful retrieval of payment pipeline."""
        mock_result = {
            "pending_authorization": 5,
            "authorized": 10,
            "pending_capture": 3,
            "captured": 20,
            "failed": 2,
            "refunded": 1,
            "overdue_authorizations": 0,
            "overdue_captures": 1,
            "total_captured_cents": 200000,
            "total_refunded_cents": 5000,
            "net_revenue_cents": 195000,
            "platform_fees_cents": 30000,
            "instructor_payouts_cents": 170000,
        }

        with patch(
            "app.services.admin_ops_service.AdminOpsService._query_payment_pipeline",
            return_value=mock_result,
        ):
            res = client.get(
                "/api/v1/admin/mcp/ops/payments/pipeline",
                headers=mcp_service_headers,
            )

        assert res.status_code == 200
        data = res.json()

        assert data["pending_authorization"] == 5
        assert data["authorized"] == 10
        assert data["total_captured_cents"] == 200000
        assert "checked_at" in data

    def test_get_payment_pipeline_requires_auth(self, client: TestClient):
        """Test that endpoint requires authentication."""
        res = client.get("/api/v1/admin/mcp/ops/payments/pipeline")
        assert res.status_code == 401


class TestPendingPayoutsEndpoint:
    """Tests for GET /api/v1/admin/mcp/ops/payments/pending-payouts"""

    def test_get_pending_payouts_success(
        self, client: TestClient, db, mcp_service_headers
    ):
        """Test successful retrieval of pending payouts."""
        mock_payouts = [
            {
                "instructor_id": "01K2INST12345678901234",
                "instructor_name": "Sarah C.",
                "pending_amount_cents": 50000,
                "completed_lessons": 5,
                "oldest_pending_date": "2024-01-10T00:00:00Z",
                "stripe_connected": True,
            }
        ]

        with patch(
            "app.services.admin_ops_service.AdminOpsService._query_pending_payouts",
            return_value=mock_payouts,
        ):
            res = client.get(
                "/api/v1/admin/mcp/ops/payments/pending-payouts",
                headers=mcp_service_headers,
            )

        assert res.status_code == 200
        data = res.json()

        assert "payouts" in data
        assert "total_pending_cents" in data
        assert "instructor_count" in data

        assert data["instructor_count"] == 1
        assert data["total_pending_cents"] == 50000
        assert data["payouts"][0]["instructor_name"] == "Sarah C."

    def test_get_pending_payouts_with_limit(
        self, client: TestClient, db, mcp_service_headers
    ):
        """Test pending payouts with limit parameter."""
        with patch(
            "app.services.admin_ops_service.AdminOpsService._query_pending_payouts",
            return_value=[],
        ):
            res = client.get(
                "/api/v1/admin/mcp/ops/payments/pending-payouts?limit=50",
                headers=mcp_service_headers,
            )

        assert res.status_code == 200

    def test_get_pending_payouts_requires_auth(self, client: TestClient):
        """Test that endpoint requires authentication."""
        res = client.get("/api/v1/admin/mcp/ops/payments/pending-payouts")
        assert res.status_code == 401


class TestUserLookupEndpoint:
    """Tests for GET /api/v1/admin/mcp/ops/users/lookup"""

    def test_lookup_user_by_email_found(
        self, client: TestClient, db, mcp_service_headers
    ):
        """Test user lookup by email - found."""
        mock_user = {
            "user_id": "01K2USER12345678901234",
            "email": "john@example.com",
            "name": "John Smith",
            "role": "student",
            "created_at": "2024-01-01T00:00:00Z",
            "last_login": "2024-01-15T12:00:00Z",
            "is_verified": True,
            "is_founding": False,
            "total_bookings": 5,
            "total_spent_cents": 50000,
            "stripe_customer_id": "cus_test123",
            "phone": "+1234567890",
        }

        with patch(
            "app.services.admin_ops_service.AdminOpsService._query_user_lookup",
            return_value=mock_user,
        ):
            res = client.get(
                "/api/v1/admin/mcp/ops/users/lookup?identifier=john@example.com",
                headers=mcp_service_headers,
            )

        assert res.status_code == 200
        data = res.json()

        assert data["found"] is True
        assert data["user"]["email"] == "john@example.com"
        assert data["user"]["name"] == "John Smith"

    def test_lookup_user_not_found(self, client: TestClient, db, mcp_service_headers):
        """Test user lookup - not found."""
        with patch(
            "app.services.admin_ops_service.AdminOpsService._query_user_lookup",
            return_value=None,
        ):
            res = client.get(
                "/api/v1/admin/mcp/ops/users/lookup?identifier=unknown@example.com",
                headers=mcp_service_headers,
            )

        assert res.status_code == 200
        data = res.json()

        assert data["found"] is False
        assert data["user"] is None

    def test_lookup_user_missing_identifier(
        self, client: TestClient, db, mcp_service_headers
    ):
        """Test user lookup without identifier parameter."""
        res = client.get(
            "/api/v1/admin/mcp/ops/users/lookup",
            headers=mcp_service_headers,
        )

        # Missing required parameter should return 422
        assert res.status_code == 422

    def test_lookup_user_requires_auth(self, client: TestClient):
        """Test that endpoint requires authentication."""
        res = client.get("/api/v1/admin/mcp/ops/users/lookup?identifier=test")
        assert res.status_code == 401


class TestUserBookingHistoryEndpoint:
    """Tests for GET /api/v1/admin/mcp/ops/users/{user_id}/bookings"""

    def test_get_user_booking_history_success(
        self, client: TestClient, db, mcp_service_headers
    ):
        """Test successful retrieval of user booking history."""
        mock_user_info = {
            "user_id": "01K2USER12345678901234",
            "user_name": "John Smith",
            "user_role": "student",
        }
        mock_bookings = [
            {
                "booking_id": "01K2BOOK12345678901234",
                "status": "COMPLETED",
                "booking_date": "2024-01-15",
                "start_time": "10:00:00",
                "end_time": "11:00:00",
                "student_name": "John S.",
                "instructor_name": "Sarah C.",
                "service_name": "Piano Lesson",
                "category": "Music",
                "total_cents": 10000,
                "location_type": "STUDENT_LOCATION",
                "created_at": "2024-01-15T09:00:00Z",
            }
        ]

        with patch(
            "app.services.admin_ops_service.AdminOpsService._query_user_booking_history",
            return_value=(mock_user_info, mock_bookings),
        ):
            res = client.get(
                "/api/v1/admin/mcp/ops/users/01K2USER12345678901234/bookings",
                headers=mcp_service_headers,
            )

        assert res.status_code == 200
        data = res.json()

        assert data["user_id"] == "01K2USER12345678901234"
        assert data["user_name"] == "John Smith"
        assert data["user_role"] == "student"
        assert data["total_count"] == 1
        assert data["bookings"][0]["service_name"] == "Piano Lesson"

    def test_get_user_booking_history_user_not_found(
        self, client: TestClient, db, mcp_service_headers
    ):
        """Test user booking history when user not found."""
        with patch(
            "app.services.admin_ops_service.AdminOpsService._query_user_booking_history",
            return_value=(None, []),
        ):
            res = client.get(
                "/api/v1/admin/mcp/ops/users/01K2UNKNOWN00000000000/bookings",
                headers=mcp_service_headers,
            )

        assert res.status_code == 200
        data = res.json()

        assert data["user_id"] == "01K2UNKNOWN00000000000"
        assert data["user_name"] == ""
        assert data["bookings"] == []

    def test_get_user_booking_history_with_limit(
        self, client: TestClient, db, mcp_service_headers
    ):
        """Test user booking history with limit parameter."""
        with patch(
            "app.services.admin_ops_service.AdminOpsService._query_user_booking_history",
            return_value=(None, []),
        ):
            res = client.get(
                "/api/v1/admin/mcp/ops/users/01K2USER12345678901234/bookings?limit=50",
                headers=mcp_service_headers,
            )

        assert res.status_code == 200

    def test_get_user_booking_history_requires_auth(self, client: TestClient):
        """Test that endpoint requires authentication."""
        res = client.get(
            "/api/v1/admin/mcp/ops/users/01K2USER12345678901234/bookings"
        )
        assert res.status_code == 401


class TestAllEndpointsAuth:
    """Test authentication requirements for all endpoints."""

    def test_endpoints_reject_invalid_token(self, client: TestClient):
        """Test that all endpoints reject invalid tokens."""
        endpoints = [
            "/api/v1/admin/mcp/ops/bookings/summary",
            "/api/v1/admin/mcp/ops/bookings/recent",
            "/api/v1/admin/mcp/ops/payments/pipeline",
            "/api/v1/admin/mcp/ops/payments/pending-payouts",
            "/api/v1/admin/mcp/ops/users/lookup?identifier=test",
            "/api/v1/admin/mcp/ops/users/01K2TEST12345678901234/bookings",
        ]

        for endpoint in endpoints:
            res = client.get(
                endpoint,
                headers={"Authorization": "Bearer invalid-token"},
            )
            assert res.status_code == 401, f"Endpoint {endpoint} should reject invalid token"
