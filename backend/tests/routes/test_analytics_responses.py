"""
Tests for analytics endpoint response models.

This verifies that all analytics endpoints return properly structured
responses using the standardized response schemas.
"""

from datetime import datetime, timedelta, timezone
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_password_hash
from app.core.enums import RoleName
from app.models.search_event import SearchEvent
from app.models.search_history import SearchHistory
from app.models.user import User
from app.services.permission_service import PermissionService


class TestAnalyticsResponseSchemas:
    """Test that all analytics endpoints return proper response schemas."""

    @pytest.fixture
    def admin_user(self, db: Session, test_password: str) -> User:
        """Create an admin user for testing."""
        # Check if user already exists and delete it
        existing_user = db.query(User).filter(User.email == "test.admin@example.com").first()
        if existing_user:
            db.delete(existing_user)
            db.commit()

        admin = User(
            email="test.admin@example.com",
            hashed_password=get_password_hash(test_password),
            first_name="Test",
            last_name="Admin",
            phone="+12125550000",
            zip_code="10001",
            is_active=True,
        )
        db.add(admin)
        db.flush()

        # Assign admin role
        permission_service = PermissionService(db)
        permission_service.assign_role(admin.id, RoleName.ADMIN)
        db.refresh(admin)
        db.commit()
        return admin

    @pytest.fixture
    def admin_headers(self, admin_user: User) -> dict:
        """Get admin authentication headers."""
        token = create_access_token({"sub": admin_user.id, "email": admin_user.email})
        return {"Authorization": f"Bearer {token}"}

    @pytest.fixture
    def sample_search_data(self, db: Session, admin_user: User):
        """Create sample search data for testing."""
        # Use UUID to ensure unique data
        unique_id = uuid.uuid4().hex[:8]

        # Create search events
        for i in range(5):
            event = SearchEvent(
                user_id=admin_user.id if i % 2 == 0 else None,
                guest_session_id=f"guest_{unique_id}_{i}" if i % 2 == 1 else None,
                search_query=f"test query {i}",
                search_type="natural_language",
                results_count=i * 5,
                referrer="/home" if i % 3 == 0 else "/browse",
                searched_at=datetime.now(timezone.utc) - timedelta(days=i),
            )
            db.add(event)

        # Create search history
        for i in range(3):
            history = SearchHistory(
                user_id=admin_user.id if i == 0 else None,
                guest_session_id=f"guest_hist_{unique_id}_{i}" if i > 0 else None,
                search_query=f"history query {unique_id} {i}",
                normalized_query=f"history query {unique_id} {i}".lower(),
                search_type="natural_language",
                search_count=i + 1,
                first_searched_at=datetime.now(timezone.utc) - timedelta(days=i * 2),
                last_searched_at=datetime.now(timezone.utc) - timedelta(days=i),
            )
            db.add(history)

        db.commit()

    def test_search_trends_response_schema(self, client: TestClient, admin_headers: dict, sample_search_data):
        """Test that search trends endpoint returns SearchTrendsResponse."""
        response = client.get(
            "/api/v1/analytics/search/search-trends?days=7",
            headers=admin_headers,
        )
        assert response.status_code == 200

        # Verify response structure
        data = response.json()
        assert isinstance(data, list)
        if data:  # If we have data
            trend = data[0]
            assert "date" in trend
            assert "total_searches" in trend
            assert "unique_users" in trend
            assert "unique_guests" in trend
            assert isinstance(trend["total_searches"], int)
            assert isinstance(trend["unique_users"], int)
            assert isinstance(trend["unique_guests"], int)

    def test_popular_searches_response_schema(self, client: TestClient, admin_headers: dict, sample_search_data):
        """Test that popular searches endpoint returns PopularSearchesResponse."""
        response = client.get(
            "/api/v1/analytics/search/popular-searches?days=7&limit=10",
            headers=admin_headers,
        )
        assert response.status_code == 200

        # Verify response structure
        data = response.json()
        assert isinstance(data, list)
        if data:  # If we have data
            search = data[0]
            assert "query" in search
            assert "search_count" in search
            assert "unique_users" in search
            assert "average_results" in search
            assert isinstance(search["search_count"], int)
            assert isinstance(search["unique_users"], int)
            assert isinstance(search["average_results"], (int, float))

    def test_search_referrers_response_schema(self, client: TestClient, admin_headers: dict, sample_search_data):
        """Test that search referrers endpoint returns SearchReferrersResponse."""
        response = client.get(
            "/api/v1/analytics/search/referrers?days=7",
            headers=admin_headers,
        )
        assert response.status_code == 200

        # Verify response structure
        data = response.json()
        assert isinstance(data, list)
        if data:  # If we have data
            referrer = data[0]
            assert "page" in referrer
            assert "search_count" in referrer
            assert "unique_sessions" in referrer
            assert "search_types" in referrer
            assert isinstance(referrer["search_count"], int)
            assert isinstance(referrer["unique_sessions"], int)
            assert isinstance(referrer["search_types"], list)

    def test_search_analytics_summary_response_schema(
        self, client: TestClient, admin_headers: dict, sample_search_data
    ):
        """Test that analytics summary endpoint returns SearchAnalyticsSummaryResponse."""
        response = client.get(
            "/api/v1/analytics/search/search-analytics-summary?days=7",
            headers=admin_headers,
        )
        assert response.status_code == 200

        # Verify response structure
        data = response.json()
        assert "date_range" in data
        assert "totals" in data
        assert "users" in data
        assert "search_types" in data
        assert "conversions" in data
        assert "performance" in data

        # Check nested structures
        assert "start" in data["date_range"]
        assert "end" in data["date_range"]
        assert "days" in data["date_range"]

        assert "total_searches" in data["totals"]
        assert "unique_users" in data["totals"]
        assert "unique_guests" in data["totals"]

        assert "authenticated" in data["users"]
        assert "guests" in data["users"]
        assert "user_percentage" in data["users"]

    def test_conversion_metrics_response_schema(self, client: TestClient, admin_headers: dict, sample_search_data):
        """Test that conversion metrics endpoint returns ConversionMetricsResponse."""
        response = client.get(
            "/api/v1/analytics/search/conversion-metrics?days=7",
            headers=admin_headers,
        )
        assert response.status_code == 200

        # Verify response structure
        data = response.json()
        assert "period" in data
        assert "guest_sessions" in data
        assert "conversion_behavior" in data
        assert "guest_engagement" in data

        # Check nested structures
        assert "start" in data["period"]
        assert "end" in data["period"]
        assert "days" in data["period"]

        assert "total" in data["guest_sessions"]
        assert "converted" in data["guest_sessions"]
        assert "conversion_rate" in data["guest_sessions"]

    def test_search_performance_response_schema(self, client: TestClient, admin_headers: dict, sample_search_data):
        """Test that search performance endpoint returns SearchPerformanceResponse."""
        response = client.get(
            "/api/v1/analytics/search/search-performance?days=7",
            headers=admin_headers,
        )
        assert response.status_code == 200

        # Verify response structure
        data = response.json()
        assert "result_distribution" in data
        assert "effectiveness" in data
        assert "problematic_queries" in data

        # Check result distribution
        dist = data["result_distribution"]
        assert "zero_results" in dist
        assert "1_5_results" in dist
        assert "6_10_results" in dist
        assert "over_10_results" in dist

        # Check effectiveness
        eff = data["effectiveness"]
        assert "avg_results_per_search" in eff
        assert "median_results" in eff
        assert "searches_with_results" in eff
        assert "zero_result_rate" in eff

    def test_export_analytics_response_schema(self, client: TestClient, admin_headers: dict):
        """Test that export analytics endpoint returns ExportAnalyticsResponse."""
        response = client.post(
            "/api/v1/analytics/export?format=csv",
            headers=admin_headers,
        )
        assert response.status_code == 200

        # Verify response structure
        data = response.json()
        assert "message" in data
        assert "format" in data
        assert "user" in data
        assert "status" in data
        assert "download_url" in data

        # Check expected values
        assert data["format"] == "csv"
        assert data["status"] == "Not implemented"
        assert data["download_url"] is None

    def test_unauthorized_access(self, client: TestClient):
        """Test that analytics endpoints require proper permissions."""
        endpoints = [
            "/api/v1/analytics/search/search-trends",
            "/api/v1/analytics/search/popular-searches",
            "/api/v1/analytics/search/referrers",
            "/api/v1/analytics/search/search-analytics-summary",
            "/api/v1/analytics/search/conversion-metrics",
            "/api/v1/analytics/search/search-performance",
        ]

        for endpoint in endpoints:
            response = client.get(endpoint)
            assert response.status_code == 401  # Unauthorized
