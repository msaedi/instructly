# backend/tests/integration/test_search_tracking_e2e.py
"""
End-to-end tests for search tracking flows.

Tests the complete flow from user performing a search to search event being recorded,
covering all 5 search types for both logged-in and guest accounts (10 scenarios).
Also tests interaction tracking with correct time calculations and different interaction types.
"""

import time
from typing import Optional
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.main import fastapi_app as app
from app.models.search_event import SearchEvent
from app.models.search_history import SearchHistory
from app.models.search_interaction import SearchInteraction
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
def guest_headers():
    """Get headers for guest requests."""
    import uuid

    # Generate unique guest session ID for each test
    return {"X-Guest-Session-ID": f"test-guest-{uuid.uuid4().hex[:8]}"}


@pytest.fixture
def test_user_with_token(db: Session):
    """Create a test user with auth token."""
    from app.auth import create_access_token

    # Create user
    user = User(
        email="e2e-test@example.com",
        first_name="E2E",
        last_name="Test User",
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


@pytest.fixture
def mock_device_context():
    """Mock device context for analytics."""
    return {
        "device_type": "desktop",
        "viewport_size": "1920x1080",
        "screen_resolution": "1920x1080",
        "connection_type": "wifi",
        "connection_effective_type": "4g",
        "language": "en-US",
        "timezone": "America/New_York",
    }


@pytest.fixture
def test_instructor(db: Session):
    """Create a test instructor user for interaction tracking."""
    from app.auth import get_password_hash
    from app.models.instructor import InstructorProfile

    # Create instructor user
    instructor_user = User(
        email="test-instructor@example.com",
        first_name="Test",
        last_name="Instructor",
        phone="+12125550000",
        zip_code="10001",
        hashed_password=get_password_hash("password123"),
    )
    db.add(instructor_user)
    db.commit()
    db.refresh(instructor_user)

    # Create instructor profile
    profile = InstructorProfile(user_id=instructor_user.id, bio="Test instructor for e2e tests", years_experience=5)
    db.add(profile)
    db.commit()

    return instructor_user


class TestSearchTypeE2E:
    """Test all 5 search types end-to-end for both authenticated and guest users."""

    def _verify_search_event(
        self,
        db: Session,
        user_id: Optional[int],
        guest_session_id: Optional[str],
        search_query: str,
        search_type: str,
        results_count: Optional[int] = None,
        referrer: Optional[str] = None,
    ) -> SearchEvent:
        """Verify a search event was created correctly."""
        query = db.query(SearchEvent)

        if user_id:
            query = query.filter(SearchEvent.user_id == user_id)
        if guest_session_id:
            query = query.filter(SearchEvent.guest_session_id == guest_session_id)

        event = query.filter(SearchEvent.search_query == search_query, SearchEvent.search_type == search_type).first()

        assert event is not None, f"Search event not found for query '{search_query}' type '{search_type}'"

        if results_count is not None:
            assert event.results_count == results_count
        if referrer is not None:
            assert event.referrer == referrer

        return event

    def _verify_search_history(
        self,
        db: Session,
        user_id: Optional[int],
        guest_session_id: Optional[str],
        search_query: str,
        search_type: str,
    ) -> SearchHistory:
        """Verify a search history entry was created correctly."""
        query = db.query(SearchHistory)

        if user_id:
            query = query.filter(SearchHistory.user_id == user_id)
        if guest_session_id:
            query = query.filter(SearchHistory.guest_session_id == guest_session_id)

        history = query.filter(
            SearchHistory.search_query == search_query, SearchHistory.search_type == search_type
        ).first()

        assert history is not None, f"Search history not found for query '{search_query}' type '{search_type}'"
        return history

    @pytest.mark.parametrize("auth_type", ["authenticated", "guest"])
    def test_type1_natural_language_search_e2e(
        self, client, db, auth_type, auth_headers, guest_headers, test_user_with_token, mock_device_context
    ):
        """Test #1: Natural language search from search bar."""
        headers = auth_headers if auth_type == "authenticated" else guest_headers
        headers["X-Session-ID"] = f"session-{auth_type}-nl"
        headers["X-Search-Origin"] = "/home"

        # Perform search
        search_data = {
            "search_query": f"piano teacher near me - {auth_type}",
            "search_type": "natural_language",
            "results_count": 15,
            "device_context": mock_device_context,
        }

        response = client.post("/api/search-history/", json=search_data, headers=headers)
        assert response.status_code == 201

        data = response.json()
        assert "search_event_id" in data
        assert data["search_event_id"] is not None

        # Verify database records
        user_id = test_user_with_token[0].id if auth_type == "authenticated" else None
        guest_id = guest_headers.get("X-Guest-Session-ID") if auth_type == "guest" else None

        event = self._verify_search_event(
            db,
            user_id,
            guest_id,
            f"piano teacher near me - {auth_type}",
            "natural_language",
            results_count=15,
            referrer="/home",
        )

        history = self._verify_search_history(
            db, user_id, guest_id, f"piano teacher near me - {auth_type}", "natural_language"
        )

        # Verify deduplication (search again)
        response2 = client.post("/api/search-history/", json=search_data, headers=headers)
        assert response2.status_code == 201

        # Should still have only one history entry
        query = db.query(SearchHistory).filter(SearchHistory.search_query == f"piano teacher near me - {auth_type}")
        if auth_type == "authenticated":
            query = query.filter(SearchHistory.user_id == user_id)
        else:
            query = query.filter(SearchHistory.guest_session_id == guest_id)
        history_count = query.count()
        assert history_count == 1

        # But should have two events
        query = db.query(SearchEvent).filter(SearchEvent.search_query == f"piano teacher near me - {auth_type}")
        if auth_type == "authenticated":
            query = query.filter(SearchEvent.user_id == user_id)
        else:
            query = query.filter(SearchEvent.guest_session_id == guest_id)
        event_count = query.count()
        assert event_count == 2

    @pytest.mark.parametrize("auth_type", ["authenticated", "guest"])
    def test_type2_category_selection_e2e(
        self, client, db, auth_type, auth_headers, guest_headers, test_user_with_token
    ):
        """Test #2: Category selection from homepage."""
        headers = auth_headers if auth_type == "authenticated" else guest_headers
        headers["X-Session-ID"] = f"session-{auth_type}-cat"
        headers["X-Search-Origin"] = "/"

        # Click on Music category
        search_data = {
            "search_query": "Music lessons",
            "search_type": "category",
            "results_count": None,  # Categories don't have results initially
        }

        response = client.post("/api/search-history/", json=search_data, headers=headers)
        assert response.status_code == 201

        # Verify records
        user_id = test_user_with_token[0].id if auth_type == "authenticated" else None
        guest_id = guest_headers.get("X-Guest-Session-ID") if auth_type == "guest" else None

        event = self._verify_search_event(
            db, user_id, guest_id, "Music lessons", "category", results_count=0, referrer="/"  # None becomes 0
        )

        # Categories should still be tracked in search_history
        self._verify_search_history(db, user_id, guest_id, "Music lessons", "category")

    @pytest.mark.parametrize("auth_type", ["authenticated", "guest"])
    def test_type3_service_pill_homepage_e2e(
        self, client, db, auth_type, auth_headers, guest_headers, test_user_with_token
    ):
        """Test #3: Service pills on homepage (top 7 services)."""
        headers = auth_headers if auth_type == "authenticated" else guest_headers
        headers["X-Session-ID"] = f"session-{auth_type}-pill"
        headers["X-Search-Origin"] = "/"

        # Click on Piano service pill
        search_data = {
            "search_query": "Piano",
            "search_type": "service_pill",
            "results_count": 12,
        }

        response = client.post("/api/search-history/", json=search_data, headers=headers)
        assert response.status_code == 201

        # Verify records
        user_id = test_user_with_token[0].id if auth_type == "authenticated" else None
        guest_id = guest_headers.get("X-Guest-Session-ID") if auth_type == "guest" else None

        event = self._verify_search_event(
            db, user_id, guest_id, "Piano", "service_pill", results_count=12, referrer="/"
        )

    @pytest.mark.parametrize("auth_type", ["authenticated", "guest"])
    def test_type4_services_page_e2e(self, client, db, auth_type, auth_headers, guest_headers, test_user_with_token):
        """Test #4: Service selection from /services page."""
        headers = auth_headers if auth_type == "authenticated" else guest_headers
        headers["X-Session-ID"] = f"session-{auth_type}-svc"
        headers["X-Search-Origin"] = "/services"

        # Click on Violin from services page
        search_data = {
            "search_query": "Violin",
            "search_type": "service_pill",  # Services page uses service_pill type
            "results_count": 8,
        }

        response = client.post("/api/search-history/", json=search_data, headers=headers)
        assert response.status_code == 201

        # Verify records
        user_id = test_user_with_token[0].id if auth_type == "authenticated" else None
        guest_id = guest_headers.get("X-Guest-Session-ID") if auth_type == "guest" else None

        event = self._verify_search_event(
            db, user_id, guest_id, "Violin", "service_pill", results_count=8, referrer="/services"
        )

    @pytest.mark.parametrize("auth_type", ["authenticated", "guest"])
    def test_type5_search_history_e2e(self, client, db, auth_type, auth_headers, guest_headers, test_user_with_token):
        """Test #5: Clicking on recent search history."""
        headers = auth_headers if auth_type == "authenticated" else guest_headers
        headers["X-Session-ID"] = f"session-{auth_type}-hist"
        headers["X-Search-Origin"] = "/"

        # First, create a search to have history
        initial_search = {
            "search_query": f"guitar lessons - {auth_type}",
            "search_type": "natural_language",
            "results_count": 10,
        }

        response = client.post("/api/search-history/", json=initial_search, headers=headers)
        assert response.status_code == 201

        # Now click on the recent search
        search_data = {
            "search_query": f"guitar lessons - {auth_type}",
            "search_type": "search_history",
            "results_count": 10,
        }

        response = client.post("/api/search-history/", json=search_data, headers=headers)
        assert response.status_code == 201

        # Verify records
        user_id = test_user_with_token[0].id if auth_type == "authenticated" else None
        guest_id = guest_headers.get("X-Guest-Session-ID") if auth_type == "guest" else None

        # Should have events for both search types
        query = db.query(SearchEvent).filter(SearchEvent.search_query == f"guitar lessons - {auth_type}")
        if auth_type == "authenticated":
            query = query.filter(SearchEvent.user_id == user_id)
        else:
            query = query.filter(SearchEvent.guest_session_id == guest_id)
        events = query.all()

        assert len(events) == 2
        search_types = [e.search_type for e in events]
        assert "natural_language" in search_types
        assert "search_history" in search_types


class TestSearchDeduplicationE2E:
    """Test search deduplication works correctly in e2e scenarios."""

    def test_deduplication_same_query_different_types(self, client, db, auth_headers, test_user_with_token):
        """Test that same query with different search types is deduplicated in history but tracked as separate events."""
        user = test_user_with_token[0]
        headers = {**auth_headers, "X-Session-ID": "dedup-session"}

        # Search "Piano" as natural language
        search1 = {
            "search_query": "Piano",
            "search_type": "natural_language",
            "results_count": 20,
        }

        response1 = client.post("/api/search-history/", json=search1, headers=headers)
        assert response1.status_code == 201

        # Search "Piano" as service pill
        search2 = {
            "search_query": "Piano",
            "search_type": "service_pill",
            "results_count": 15,
        }

        response2 = client.post("/api/search-history/", json=search2, headers=headers)
        assert response2.status_code == 201

        # Should have only 1 history entry (deduplicated by query)
        history_entries = (
            db.query(SearchHistory)
            .filter(SearchHistory.search_query == "Piano", SearchHistory.user_id == user.id)
            .all()
        )

        assert len(history_entries) == 1
        # The search_type in history will be from the first search
        assert history_entries[0].search_type == "natural_language"
        assert history_entries[0].search_count == 2  # Incremented

        # But should have 2 events with different types
        events = db.query(SearchEvent).filter(SearchEvent.search_query == "Piano", SearchEvent.user_id == user.id).all()
        assert len(events) == 2
        event_types = [e.search_type for e in events]
        assert "natural_language" in event_types
        assert "service_pill" in event_types

    def test_deduplication_rapid_searches(self, client, db, auth_headers):
        """Test deduplication when user performs rapid searches."""
        headers = {**auth_headers, "X-Session-ID": "rapid-session"}

        search_data = {
            "search_query": "yoga instructor",
            "search_type": "natural_language",
            "results_count": 5,
        }

        # Simulate rapid searches (e.g., from debounced search input)
        for i in range(5):
            response = client.post("/api/search-history/", json=search_data, headers=headers)
            assert response.status_code == 201

        # Should only have 1 history entry
        history_count = db.query(SearchHistory).filter(SearchHistory.search_query == "yoga instructor").count()
        assert history_count == 1

        # But should have 5 events for analytics
        event_count = db.query(SearchEvent).filter(SearchEvent.search_query == "yoga instructor").count()
        assert event_count == 5


class TestSearchInteractionE2E:
    """Test search interaction tracking end-to-end."""

    def test_interaction_tracking_with_time(self, client, db, auth_headers, test_instructor):
        """Test interaction tracking with correct time calculation."""
        headers = {**auth_headers, "X-Session-ID": "interaction-session"}

        # Step 1: Perform a search
        search_data = {
            "search_query": "dance instructor",
            "search_type": "natural_language",
            "results_count": 8,
        }

        search_response = client.post("/api/search-history/", json=search_data, headers=headers)
        assert search_response.status_code == 201

        search_result = search_response.json()
        search_event_id = search_result["search_event_id"]
        assert search_event_id is not None

        # Step 2: Simulate time passing (3 seconds)
        time.sleep(3)

        # Step 3: Track interaction (click on result)
        interaction_data = {
            "search_event_id": search_event_id,
            "interaction_type": "click",
            "instructor_id": test_instructor.id,  # Use real instructor ID
            "result_position": 2,  # Second result
            "time_to_interaction": 3.0,  # 3 seconds
        }

        interaction_response = client.post("/api/search-history/interaction", json=interaction_data, headers=headers)
        assert interaction_response.status_code == 201

        # Verify interaction was recorded
        interaction = db.query(SearchInteraction).filter(SearchInteraction.search_event_id == search_event_id).first()

        assert interaction is not None
        assert interaction.interaction_type == "click"
        assert interaction.instructor_id == test_instructor.id
        assert interaction.result_position == 2
        assert interaction.time_to_interaction == 3.0

    def test_multiple_interaction_types(self, client, db, auth_headers, test_instructor):
        """Test different interaction types on same search."""
        headers = {**auth_headers, "X-Session-ID": "multi-interaction"}

        # Perform search
        search_data = {
            "search_query": "math tutor",
            "search_type": "natural_language",
            "results_count": 10,
        }

        search_response = client.post("/api/search-history/", json=search_data, headers=headers)
        search_event_id = search_response.json()["search_event_id"]

        # Track different interactions
        interactions = [
            ("hover", 1, 0.5),  # Hover on first result after 0.5s
            ("click", 1, 2.0),  # Click on first result after 2s
            ("view_profile", 1, 5.0),  # View profile after 5s
            ("book", 1, 30.0),  # Book after 30s
        ]

        for interaction_type, position, time_elapsed in interactions:
            interaction_data = {
                "search_event_id": search_event_id,
                "interaction_type": interaction_type,
                "instructor_id": test_instructor.id,
                "result_position": position,
                "time_to_interaction": time_elapsed,
            }

            response = client.post("/api/search-history/interaction", json=interaction_data, headers=headers)
            assert response.status_code == 201

        # Verify all interactions were recorded
        db_interactions = db.query(SearchInteraction).filter(SearchInteraction.search_event_id == search_event_id).all()

        assert len(db_interactions) == 4

        interaction_types = [i.interaction_type for i in db_interactions]
        assert "hover" in interaction_types
        assert "click" in interaction_types
        assert "view_profile" in interaction_types
        assert "book" in interaction_types

    def test_guest_interaction_tracking(self, client, db, guest_headers, test_instructor):
        """Test that guest users can track interactions."""
        headers = {**guest_headers, "X-Session-ID": "guest-interaction"}

        # Guest performs search
        search_data = {
            "search_query": "cooking instructor",
            "search_type": "natural_language",
            "results_count": 6,
        }

        search_response = client.post("/api/search-history/", json=search_data, headers=headers)
        assert search_response.status_code == 201

        search_event_id = search_response.json()["search_event_id"]

        # Guest clicks on result
        interaction_data = {
            "search_event_id": search_event_id,
            "interaction_type": "click",
            "instructor_id": test_instructor.id,
            "result_position": 3,
            "time_to_interaction": 4.5,
        }

        interaction_response = client.post("/api/search-history/interaction", json=interaction_data, headers=headers)
        assert interaction_response.status_code == 201

        # Verify guest interaction was recorded
        interaction = db.query(SearchInteraction).filter(SearchInteraction.search_event_id == search_event_id).first()

        assert interaction is not None

        # Verify the search event has guest session ID
        event = db.query(SearchEvent).filter(SearchEvent.id == search_event_id).first()

        assert event is not None
        assert event.guest_session_id == guest_headers.get("X-Guest-Session-ID")
        assert event.user_id is None


class TestSearchAnalyticsE2E:
    """Test analytics data collection end-to-end."""

    def test_device_context_collection(self, client, db, auth_headers):
        """Test that device context is properly collected."""
        headers = {**auth_headers, "X-Session-ID": "device-context"}

        device_context = {
            "device_type": "mobile",
            "viewport_size": "375x812",
            "screen_resolution": "1125x2436",
            "connection_type": "cellular",
            "connection_effective_type": "3g",
            "language": "es-ES",
            "timezone": "Europe/Madrid",
        }

        search_data = {
            "search_query": "Spanish tutor",
            "search_type": "natural_language",
            "results_count": 4,
            "device_context": device_context,
        }

        response = client.post("/api/search-history/", json=search_data, headers=headers)
        assert response.status_code == 201

        # Verify device context was stored
        event = db.query(SearchEvent).filter(SearchEvent.search_query == "Spanish tutor").first()

        assert event is not None
        assert event.device_type == "mobile"
        assert event.connection_type == "cellular"
        # Browser info should contain additional context
        assert event.browser_info is not None
        assert "viewport" in event.browser_info
        assert event.browser_info["viewport"] == "375x812"

    @patch("app.services.geolocation_service.GeolocationService.get_location_from_ip")
    async def test_geolocation_tracking(self, mock_geo, client, db, auth_headers):
        """Test that geolocation is tracked from IP."""
        # Mock geolocation service
        mock_geo.return_value = {
            "country": "US",
            "region": "CA",
            "city": "San Francisco",
            "timezone": "America/Los_Angeles",
        }

        headers = {
            **auth_headers,
            "X-Session-ID": "geo-session",
            "X-Forwarded-For": "8.8.8.8",  # Public IP for geo lookup
        }

        search_data = {
            "search_query": "surf instructor",
            "search_type": "natural_language",
            "results_count": 3,
        }

        response = client.post("/api/search-history/", json=search_data, headers=headers)
        assert response.status_code == 201

        # Verify geo data was stored
        event = db.query(SearchEvent).filter(SearchEvent.search_query == "surf instructor").first()

        assert event is not None
        # IP should be hashed, not stored raw
        assert event.ip_address is None
        assert event.ip_address_hash is not None

        # Geo data should be stored
        assert event.geo_data is not None
        assert event.geo_data.get("city") == "San Francisco"

    def test_session_continuity_tracking(self, client, db, auth_headers):
        """Test that searches within same session are linked."""
        session_id = "journey-session-123"
        headers = {**auth_headers, "X-Session-ID": session_id}

        # User journey: category -> natural language -> click recent
        searches = [
            {
                "search_query": "Fitness",
                "search_type": "category",
                "results_count": 25,
                "headers": {**headers, "X-Search-Origin": "/"},
            },
            {
                "search_query": "personal trainer downtown",
                "search_type": "natural_language",
                "results_count": 8,
                "headers": {**headers, "X-Search-Origin": "/search?category=Fitness"},
            },
            {
                "search_query": "personal trainer downtown",
                "search_type": "search_history",
                "results_count": 8,
                "headers": {**headers, "X-Search-Origin": "/"},
            },
        ]

        for search in searches:
            headers_with_origin = search.pop("headers")
            response = client.post("/api/search-history/", json=search, headers=headers_with_origin)
            assert response.status_code == 201

        # Verify all searches have same session ID
        events = (
            db.query(SearchEvent).filter(SearchEvent.session_id == session_id).order_by(SearchEvent.searched_at).all()
        )

        assert len(events) == 3

        # Verify search journey
        assert events[0].search_type == "category"
        assert events[1].search_type == "natural_language"
        assert events[2].search_type == "search_history"

        # Verify referrers show navigation flow
        assert events[0].referrer == "/"
        assert events[1].referrer == "/search?category=Fitness"
        assert events[2].referrer == "/"
