# backend/tests/integration/test_search_interaction_endpoint.py
"""
Integration test for search interaction tracking endpoint.

Tests the /api/search-history/interaction endpoint to ensure
it properly saves search interactions to the database.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.search_event import SearchEvent
from app.models.search_interaction import SearchInteraction

# Use the test_instructor fixture from conftest.py instead


@pytest.fixture
def test_search_event(db: Session, test_student):
    """Create a test search event."""
    event = SearchEvent(
        user_id=test_student.id,
        search_query="piano lessons",
        search_type="natural_language",
        results_count=10,
        session_id="test-session-123",
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@pytest.mark.integration
class TestSearchInteractionEndpoint:
    """Test cases for search interaction tracking endpoint."""

    def test_track_interaction_authenticated(
        self, client: TestClient, test_student, test_search_event, test_instructor, auth_headers_student, db
    ):
        """Test tracking interaction as authenticated user."""

        # Track interaction
        interaction_data = {
            "search_event_id": test_search_event.id,
            "interaction_type": "click",
            "instructor_id": test_instructor.id,
            "result_position": 3,
            "time_to_interaction": 2.5,
        }

        response = client.post(
            "/api/search-history/interaction",
            json=interaction_data,
            headers={**auth_headers_student, "X-Session-ID": "test-session-123"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "tracked"
        assert "interaction_id" in data

        # Verify in database
        interaction = db.query(SearchInteraction).filter_by(id=data["interaction_id"]).first()
        assert interaction is not None
        assert interaction.search_event_id == test_search_event.id
        assert interaction.interaction_type == "click"
        assert interaction.instructor_id == test_instructor.id
        assert interaction.result_position == 3
        assert interaction.time_to_interaction == 2.5

    def test_track_interaction_guest(self, client: TestClient, test_search_event, test_instructor, db):
        """Test tracking interaction as guest user."""
        # Create search event for guest
        guest_event = SearchEvent(
            guest_session_id="guest-123",
            search_query="guitar lessons",
            search_type="natural_language",
            results_count=5,
            session_id="browser-session-456",
        )
        db.add(guest_event)
        db.commit()
        db.refresh(guest_event)

        # Track interaction
        interaction_data = {
            "search_event_id": guest_event.id,
            "interaction_type": "hover",
            "instructor_id": test_instructor.id,
            "result_position": 1,
            "time_to_interaction": 0.5,
        }

        response = client.post(
            "/api/search-history/interaction",
            json=interaction_data,
            headers={"X-Guest-Session-ID": "guest-123", "X-Session-ID": "browser-session-456"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "tracked"

        # Verify in database
        interaction = db.query(SearchInteraction).filter_by(id=data["interaction_id"]).first()
        assert interaction is not None
        assert interaction.interaction_type == "hover"
        assert interaction.session_id == "browser-session-456"

    def test_track_interaction_missing_required_fields(self, client: TestClient, auth_headers_student):
        """Test error handling for missing required fields."""

        # Missing search_event_id
        response = client.post(
            "/api/search-history/interaction",
            json={"interaction_type": "click", "instructor_id": 123},
            headers=auth_headers_student,
        )

        assert response.status_code == 400
        assert "search_event_id and interaction_type are required" in response.json()["detail"]

    def test_track_interaction_invalid_search_event(self, client: TestClient, test_instructor, auth_headers_student):
        """Test error handling for invalid search event ID."""

        # Invalid search event ID (non-existent ULID)
        invalid_ulid = "01K2H9999999999999999999999"
        response = client.post(
            "/api/search-history/interaction",
            json={"search_event_id": invalid_ulid, "interaction_type": "click", "instructor_id": test_instructor.id},
            headers=auth_headers_student,
        )

        assert response.status_code == 400
        assert f"Search event {invalid_ulid} not found" in response.json()["detail"]

    def test_track_multiple_interaction_types(
        self, client: TestClient, test_search_event, test_instructor, auth_headers_student, db
    ):
        """Test tracking different types of interactions."""

        interaction_types = ["view", "hover", "click", "view_profile", "contact"]

        for interaction_type in interaction_types:
            response = client.post(
                "/api/search-history/interaction",
                json={
                    "search_event_id": test_search_event.id,
                    "interaction_type": interaction_type,
                    "instructor_id": test_instructor.id,
                    "result_position": 1,
                },
                headers=auth_headers_student,
            )

            assert response.status_code == 201
            assert response.json()["status"] == "tracked"

        # Verify all interactions in database
        interactions = db.query(SearchInteraction).filter_by(search_event_id=test_search_event.id).all()

        assert len(interactions) == 5
        tracked_types = {i.interaction_type for i in interactions}
        assert tracked_types == set(interaction_types)
