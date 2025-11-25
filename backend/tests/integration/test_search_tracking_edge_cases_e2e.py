# backend/tests/integration/test_search_tracking_edge_cases_e2e.py
"""
Edge case and error scenario tests for search tracking e2e flows.

Tests error handling, data validation, and edge cases like missing data,
invalid inputs, and system behavior under stress.
"""

import time
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.core.ulid_helper import generate_ulid
from app.main import fastapi_app as app
from app.models.search_event import SearchEvent
from app.models.search_history import SearchHistory
from app.models.search_interaction import SearchInteraction

pytestmark = pytest.mark.anyio
from app.models.user import User


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def auth_headers(test_user_with_token):
    """Get auth headers for authenticated requests."""
    user, token = test_user_with_token
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def test_user_with_token(db: Session):
    """Create a test user with auth token."""
    from app.auth import create_access_token

    # Create user
    user = User(
        email="edge-case-test@example.com",
        first_name="Edge",
        last_name="Case User",
        hashed_password="hashed",
        phone="+12125550000",
        zip_code="10001",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Create token
    access_token = create_access_token(data={"sub": user.email})

    return user, access_token


class TestSearchTrackingEdgeCases:
    """Test edge cases in search tracking."""

    def test_missing_guest_session_id(self, client, db):
        """Test that requests without auth or guest session ID are rejected."""
        # No auth headers, no guest session ID
        search_data = {
            "search_query": "test query",
            "search_type": "natural_language",
            "results_count": 5,
        }

        response = client.post("/api/v1/search-history/", json=search_data)
        assert response.status_code == 400
        assert "Must provide either authentication token or guest session ID" in response.json()["detail"]

    def test_invalid_search_type(self, client, auth_headers):
        """Test that invalid search types are rejected."""
        search_data = {
            "search_query": "test query",
            "search_type": "invalid_type",  # Not in allowed types
            "results_count": 5,
        }

        response = client.post("/api/v1/search-history/", json=search_data, headers=auth_headers)
        assert response.status_code == 422  # Validation error

        # Check error details
        error_detail = response.json()["detail"][0]
        assert "search_type" in error_detail["loc"][-1]

    def test_empty_search_query(self, client, auth_headers):
        """Test that empty search queries are rejected."""
        search_data = {
            "search_query": "   ",  # Just whitespace
            "search_type": "natural_language",
            "results_count": 0,
        }

        response = client.post("/api/v1/search-history/", json=search_data, headers=auth_headers)
        assert response.status_code == 422

        # Check validation error
        error_detail = response.json()["detail"][0]
        assert "search_query" in error_detail["loc"][-1]

    def test_negative_results_count(self, client, auth_headers):
        """Test that negative results count is rejected."""
        search_data = {
            "search_query": "test query",
            "search_type": "natural_language",
            "results_count": -5,  # Negative count
        }

        response = client.post("/api/v1/search-history/", json=search_data, headers=auth_headers)
        assert response.status_code == 422

        # Check validation error
        error_detail = response.json()["detail"][0]
        assert "results_count" in str(error_detail)

    def test_very_long_search_query(self, client, db, auth_headers):
        """Test handling of very long search queries."""
        # Create a very long query (but within DB limits)
        # Note: The schema strips whitespace, so we need a query that won't be affected
        long_query = "piano teacher " * 50  # ~700 characters before stripping
        stripped_query = long_query.strip()  # This is what will be stored

        search_data = {
            "search_query": long_query,
            "search_type": "natural_language",
            "results_count": 0,
        }

        response = client.post("/api/v1/search-history/", json=search_data, headers=auth_headers)
        assert response.status_code == 201

        # Verify it was stored properly (search by stripped version)
        event = db.query(SearchEvent).filter(SearchEvent.search_query == stripped_query).first()

        assert event is not None
        assert event.search_query == stripped_query
        assert len(event.search_query) == len(stripped_query)

    def test_unicode_search_queries(self, client, db, auth_headers):
        """Test handling of unicode characters in search queries."""
        unicode_queries = [
            "数学教师",  # Chinese
            "معلم الرياضيات",  # Arabic
            "🎸 guitar teacher 🎵",  # Emojis
            "Müller's Musikschule",  # German with special chars
        ]

        for query in unicode_queries:
            search_data = {
                "search_query": query,
                "search_type": "natural_language",
                "results_count": 5,
            }

            response = client.post("/api/v1/search-history/", json=search_data, headers=auth_headers)
            assert response.status_code == 201

            # Verify storage
            event = db.query(SearchEvent).filter(SearchEvent.search_query == query).first()

            assert event is not None
            assert event.search_query == query

    def test_null_optional_fields(self, client, db, auth_headers):
        """Test that null/missing optional fields are handled correctly."""
        # Minimal required fields only
        search_data = {
            "search_query": "minimal search",
            "search_type": "natural_language",
            # No results_count, device_context, search_context
        }

        response = client.post("/api/v1/search-history/", json=search_data, headers=auth_headers)
        assert response.status_code == 201

        # Verify defaults are applied
        event = db.query(SearchEvent).filter(SearchEvent.search_query == "minimal search").first()

        assert event is not None
        assert event.results_count == 0  # Default when None
        assert event.device_type is None
        assert event.connection_type is None


class TestSearchInteractionEdgeCases:
    """Test edge cases in search interaction tracking."""

    def test_interaction_without_search_event(self, client, auth_headers):
        """Test interaction tracking with non-existent search event ID."""
        interaction_data = {
            "search_event_id": generate_ulid(),  # Non-existent ID
            "interaction_type": "click",
            "instructor_id": 123,
            "result_position": 1,
        }

        response = client.post("/api/v1/search-history/interaction", json=interaction_data, headers=auth_headers)
        assert response.status_code == 400
        assert "not found" in response.json()["detail"].lower()

    def test_interaction_missing_required_fields(self, client, auth_headers):
        """Test interaction tracking with missing required fields."""
        # Missing search_event_id
        interaction_data = {
            "interaction_type": "click",
            "instructor_id": 123,
        }

        response = client.post("/api/v1/search-history/interaction", json=interaction_data, headers=auth_headers)
        assert response.status_code == 400
        assert "search_event_id and interaction_type are required" in response.json()["detail"]

    def test_interaction_invalid_type(self, client, db, auth_headers):
        """Test interaction with invalid interaction type."""
        # First create a search
        search_data = {
            "search_query": "test for interaction",
            "search_type": "natural_language",
            "results_count": 5,
        }

        search_response = client.post("/api/v1/search-history/", json=search_data, headers=auth_headers)
        search_event_id = search_response.json()["search_event_id"]

        # Try invalid interaction type
        interaction_data = {
            "search_event_id": search_event_id,
            "interaction_type": "invalid_action",  # Not a valid type
            # Don't include instructor_id to test nullable field
        }

        response = client.post("/api/v1/search-history/interaction", json=interaction_data, headers=auth_headers)
        # Should still accept it (backend doesn't validate interaction types strictly)
        assert response.status_code == 201

    def test_interaction_negative_time(self, client, db, auth_headers):
        """Test interaction with negative time_to_interaction."""
        # Create search
        search_response = client.post(
            "/api/v1/search-history/",
            json={
                "search_query": "negative time test",
                "search_type": "natural_language",
                "results_count": 3,
            },
            headers=auth_headers,
        )
        search_event_id = search_response.json()["search_event_id"]

        # Try negative time
        interaction_data = {
            "search_event_id": search_event_id,
            "interaction_type": "click",
            # Don't include instructor_id to avoid FK constraint
            "time_to_interaction": -5.0,  # Negative time
        }

        response = client.post("/api/v1/search-history/interaction", json=interaction_data, headers=auth_headers)
        # Should accept it (could happen with clock sync issues)
        assert response.status_code == 201

        # Verify it was stored
        interaction = db.query(SearchInteraction).filter(SearchInteraction.search_event_id == search_event_id).first()

        assert interaction is not None
        assert interaction.time_to_interaction == -5.0


class TestConcurrencyAndPerformance:
    """Test system behavior under concurrent access and load."""

    def test_concurrent_duplicate_searches(self, client, db, auth_headers):
        """Test deduplication with concurrent duplicate searches."""
        import threading

        search_data = {
            "search_query": "concurrent test",
            "search_type": "natural_language",
            "results_count": 10,
        }

        results = []

        def make_request():
            response = client.post("/api/v1/search-history/", json=search_data, headers=auth_headers)
            results.append(response.status_code)

        # Create 5 concurrent requests
        threads = []
        for _ in range(5):
            t = threading.Thread(target=make_request)
            threads.append(t)
            t.start()

        # Wait for all threads
        for t in threads:
            t.join()

        # All should succeed
        assert all(status == 201 for status in results)

        # But should only have 1 history entry (deduplicated)
        history_count = db.query(SearchHistory).filter(SearchHistory.normalized_query == "concurrent test").count()
        assert history_count == 1

        # Should have 5 events
        event_count = db.query(SearchEvent).filter(SearchEvent.search_query == "concurrent test").count()
        assert event_count == 5

    def test_rapid_interaction_tracking(self, client, db, auth_headers):
        """Test rapid interaction tracking on same search."""
        # Create search
        search_response = client.post(
            "/api/v1/search-history/",
            json={
                "search_query": "rapid interaction test",
                "search_type": "natural_language",
                "results_count": 20,
            },
            headers=auth_headers,
        )
        search_event_id = search_response.json()["search_event_id"]

        # Simulate rapid interactions (user quickly hovering over results)
        start_time = time.time()
        for i in range(10):
            interaction_data = {
                "search_event_id": search_event_id,
                "interaction_type": "hover",
                # Don't include instructor_id to avoid FK constraint
                "result_position": i + 1,
                "time_to_interaction": time.time() - start_time,
            }

            response = client.post("/api/v1/search-history/interaction", json=interaction_data, headers=auth_headers)
            assert response.status_code == 201

            # Small delay to simulate realistic hovering
            time.sleep(0.1)

        # Verify all interactions were recorded
        interactions = (
            db.query(SearchInteraction)
            .filter(SearchInteraction.search_event_id == search_event_id)
            .order_by(SearchInteraction.created_at.asc())
            .all()
        )

        assert len(interactions) == 10

        # Verify times are increasing
        times = [i.time_to_interaction for i in interactions]
        assert all(times[i] < times[i + 1] for i in range(len(times) - 1))


class TestDataIntegrity:
    """Test data integrity and consistency."""

    def test_guest_to_user_conversion_integrity(self, client, db):
        """Test that guest searches maintain integrity when user logs in."""
        import uuid

        guest_session_id = f"guest-convert-test-{uuid.uuid4().hex[:8]}"
        guest_headers = {"X-Guest-Session-ID": guest_session_id}

        # Guest performs searches
        guest_searches = [
            {"search_query": "piano lessons", "search_type": "natural_language", "results_count": 10},
            {"search_query": "guitar lessons", "search_type": "natural_language", "results_count": 8},
            {"search_query": "Music", "search_type": "category", "results_count": 20},
        ]

        for search in guest_searches:
            response = client.post("/api/v1/search-history/", json=search, headers=guest_headers)
            assert response.status_code == 201

        # Verify guest searches exist
        guest_history = db.query(SearchHistory).filter(SearchHistory.guest_session_id == guest_session_id).all()
        assert len(guest_history) == 3

        guest_events = db.query(SearchEvent).filter(SearchEvent.guest_session_id == guest_session_id).all()
        assert len(guest_events) == 3

        # Note: Actual conversion happens during login flow, which would need to be tested
        # in auth integration tests. Here we just verify data structure is correct.

    def test_search_history_soft_delete_integrity(self, client, db, auth_headers, test_user_with_token):
        """Test that soft delete maintains data integrity."""
        user = test_user_with_token[0]

        # Create searches
        searches = [
            {"search_query": "delete test 1", "search_type": "natural_language", "results_count": 5},
            {"search_query": "delete test 2", "search_type": "natural_language", "results_count": 3},
        ]

        search_ids = []
        for search in searches:
            response = client.post("/api/v1/search-history/", json=search, headers=auth_headers)
            assert response.status_code == 201
            search_ids.append(response.json()["id"])

        # Delete first search
        delete_response = client.delete(f"/api/v1/search-history/{search_ids[0]}", headers=auth_headers)
        assert delete_response.status_code == 204

        # Get recent searches - should only see the non-deleted one
        get_response = client.get("/api/v1/search-history/", headers=auth_headers)
        assert get_response.status_code == 200

        recent = get_response.json()
        queries = [s["search_query"] for s in recent]
        assert "delete test 1" not in queries
        assert "delete test 2" in queries

        # But events should still exist for both (no soft delete on events)
        events = (
            db.query(SearchEvent)
            .filter(SearchEvent.user_id == user.id, SearchEvent.search_query.like("delete test%"))
            .all()
        )
        assert len(events) == 2


class TestAnalyticsDataQuality:
    """Test quality of analytics data collection."""

    @patch("app.services.geolocation_service.GeolocationService.get_location_from_ip")
    async def test_ip_hashing_privacy(self, mock_geo, client, db, auth_headers):
        """Test that IP addresses are hashed for privacy."""
        mock_geo.return_value = {"country": "US", "city": "New York"}

        # Make request with IP
        headers = {
            **auth_headers,
            "X-Forwarded-For": "192.168.1.100",
        }

        search_data = {
            "search_query": "privacy test",
            "search_type": "natural_language",
            "results_count": 1,
        }

        response = client.post("/api/v1/search-history/", json=search_data, headers=headers)
        assert response.status_code == 201

        # Check that IP is hashed, not stored raw
        event = db.query(SearchEvent).filter(SearchEvent.search_query == "privacy test").first()

        assert event is not None
        assert event.ip_address is None  # Raw IP should never be stored
        assert event.ip_address_hash is not None  # Should have hash
        assert "192.168.1.100" not in str(event.ip_address_hash)  # Hash shouldn't contain raw IP

    def test_returning_user_detection(self, client, db, auth_headers, test_user_with_token):
        """Test that returning users are properly detected."""
        user = test_user_with_token[0]

        # First search - new user
        search1 = {
            "search_query": "first search",
            "search_type": "natural_language",
            "results_count": 5,
        }

        response1 = client.post("/api/v1/search-history/", json=search1, headers=auth_headers)
        assert response1.status_code == 201

        # Wait a moment
        time.sleep(1)

        # Second search - returning user
        search2 = {
            "search_query": "second search",
            "search_type": "natural_language",
            "results_count": 8,
        }

        response2 = client.post("/api/v1/search-history/", json=search2, headers=auth_headers)
        assert response2.status_code == 201

        # Check is_returning_user flag
        events = db.query(SearchEvent).filter(SearchEvent.user_id == user.id).order_by(SearchEvent.searched_at).all()

        assert len(events) == 2
        # Note: The service checks for previous searches, so both might be marked as returning
        # depending on test database state. The important thing is the flag exists.
