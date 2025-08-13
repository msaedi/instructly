# backend/tests/repositories/test_search_interaction_repository.py
"""
Unit tests for SearchInteractionRepository.

Tests the repository methods for creating and querying search interactions.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.core.enums import RoleName
from app.models.rbac import Role
from app.models.search_event import SearchEvent
from app.models.user import User
from app.repositories.search_interaction_repository import SearchInteractionRepository


@pytest.fixture
def test_user(db: Session):
    """Create a test user."""
    user = User(
        email="interaction@example.com",
        first_name="Interaction",
        last_name="Test",
        hashed_password="hashed",
        phone="+12125550000",
        zip_code="10001",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def test_instructors(db: Session):
    """Create test instructors for interaction tests."""
    # First ensure instructor role exists
    instructor_role = db.query(Role).filter_by(name=RoleName.INSTRUCTOR).first()
    if not instructor_role:
        instructor_role = Role(name=RoleName.INSTRUCTOR, description="Instructor role")
        db.add(instructor_role)
        db.commit()

    instructors = []
    # Create instructors - we need at least 8 for the tests
    for i in range(8):
        user = User(
            email=f"instructor{i}@example.com",
            first_name="Test",
            last_name=f"Instructor {i}",
            hashed_password="hashed",
            phone="+12125550000",
            zip_code="10001",
        )
        db.add(user)
        db.flush()  # Get the ID

        # Add instructor role
        user.roles.append(instructor_role)
        instructors.append(user)

    db.commit()
    return instructors


@pytest.fixture
def test_search_event(db: Session, test_user):
    """Create a test search event."""
    event = SearchEvent(
        user_id=test_user.id,
        search_query="piano teacher",
        search_type="natural_language",
        results_count=10,
        session_id="test-session-123",
        searched_at=datetime.now(timezone.utc),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@pytest.fixture
def interaction_repository(db: Session):
    """Create an interaction repository instance."""
    return SearchInteractionRepository(db)


class TestSearchInteractionRepository:
    """Test cases for SearchInteractionRepository."""

    def test_create_interaction(self, interaction_repository, test_search_event, test_instructors, db):
        """Test creating a new search interaction."""
        # Use the first test instructor's actual ID
        instructor_id = test_instructors[0].id

        interaction_data = {
            "search_event_id": test_search_event.id,
            "session_id": "test-session-123",
            "interaction_type": "click",
            "instructor_id": instructor_id,
            "result_position": 3,
            "time_to_interaction": 2.5,
        }

        interaction = interaction_repository.create_interaction(interaction_data)
        db.commit()

        assert interaction.id is not None
        assert interaction.search_event_id == test_search_event.id
        assert interaction.interaction_type == "click"
        assert interaction.instructor_id == instructor_id
        assert interaction.result_position == 3
        assert interaction.time_to_interaction == 2.5

    def test_get_interactions_by_search_event(self, interaction_repository, test_search_event, test_instructors, db):
        """Test getting interactions for a specific search event."""
        # Create multiple interactions
        for i in range(5):
            interaction_data = {
                "search_event_id": test_search_event.id,
                "interaction_type": "click" if i % 2 == 0 else "hover",
                "instructor_id": test_instructors[i % len(test_instructors)].id,
                "result_position": i + 1,
                "time_to_interaction": float(i + 1),
            }
            interaction_repository.create_interaction(interaction_data)
        db.commit()

        # Get interactions
        interactions = interaction_repository.get_interactions_by_search_event(test_search_event.id)

        assert len(interactions) == 5
        # Should be ordered by created_at desc (newest first)
        # Check that all positions are present
        positions = [i.result_position for i in interactions]
        assert set(positions) == {1, 2, 3, 4, 5}

    def test_get_interactions_by_instructor(self, interaction_repository, test_search_event, test_instructors, db):
        """Test getting interactions for a specific instructor."""
        instructor_id = test_instructors[0].id

        # Create interactions for the instructor
        for i in range(3):
            interaction_data = {
                "search_event_id": test_search_event.id,
                "interaction_type": "click",
                "instructor_id": instructor_id,
                "result_position": i + 1,
            }
            interaction_repository.create_interaction(interaction_data)

        # Create interactions for other instructors
        interaction_repository.create_interaction(
            {
                "search_event_id": test_search_event.id,
                "interaction_type": "click",
                "instructor_id": test_instructors[1].id,
            }
        )
        db.commit()

        # Get interactions
        interactions = interaction_repository.get_interactions_by_instructor(instructor_id)

        assert len(interactions) == 3
        assert all(i.instructor_id == instructor_id for i in interactions)

    def test_get_click_through_rate(self, interaction_repository, test_user, test_instructors, db):
        """Test calculating click-through rate."""
        # Create search events
        event_ids = []
        for i in range(5):
            event = SearchEvent(
                user_id=test_user.id,
                search_query=f"query {i}",
                search_type="natural_language",
                results_count=10,
                searched_at=datetime.now(timezone.utc),
            )
            db.add(event)
            db.flush()
            event_ids.append(event.id)

        # Create clicks for 3 out of 5 searches
        for i in range(3):
            interaction_repository.create_interaction(
                {"search_event_id": event_ids[i], "interaction_type": "click", "instructor_id": test_instructors[0].id}
            )

        # Create non-click interactions
        interaction_repository.create_interaction(
            {"search_event_id": event_ids[3], "interaction_type": "hover", "instructor_id": test_instructors[0].id}
        )
        db.commit()

        # Calculate CTR
        ctr_data = interaction_repository.get_click_through_rate(event_ids)

        assert ctr_data["total_searches"] == 5
        assert ctr_data["total_clicks"] == 3
        assert ctr_data["ctr"] == 60.0  # 3/5 * 100

    def test_get_click_through_rate_empty(self, interaction_repository):
        """Test CTR calculation with no search events."""
        ctr_data = interaction_repository.get_click_through_rate([])

        assert ctr_data["total_searches"] == 0
        assert ctr_data["total_clicks"] == 0
        assert ctr_data["ctr"] == 0.0

    def test_get_average_position_clicked(self, interaction_repository, test_search_event, test_instructors, db):
        """Test calculating average position clicked."""
        instructor_id = test_instructors[0].id

        # Create clicks at different positions
        positions = [1, 3, 5, 2, 4]
        for pos in positions:
            interaction_repository.create_interaction(
                {
                    "search_event_id": test_search_event.id,
                    "interaction_type": "click",
                    "instructor_id": instructor_id,
                    "result_position": pos,
                }
            )

        # Create non-click interactions (should be ignored)
        interaction_repository.create_interaction(
            {
                "search_event_id": test_search_event.id,
                "interaction_type": "hover",
                "instructor_id": instructor_id,
                "result_position": 10,
            }
        )
        db.commit()

        # Get average position
        avg_position = interaction_repository.get_average_position_clicked(instructor_id)

        assert avg_position == 3.0  # (1+3+5+2+4) / 5

    def test_get_average_position_clicked_no_clicks(self, interaction_repository):
        """Test average position when there are no clicks."""
        from app.core.ulid_helper import generate_ulid

        avg_position = interaction_repository.get_average_position_clicked(generate_ulid())
        assert avg_position is None

    def test_get_interaction_funnel(self, interaction_repository, test_search_event, test_instructors, db):
        """Test getting interaction funnel for a search event."""
        # Create interactions representing a funnel
        interactions = [
            ("view", 10),
            ("hover", 8),
            ("click", 5),
            ("view_profile", 3),
            ("contact", 1),
        ]

        for interaction_type, count in interactions:
            for _ in range(count):
                interaction_repository.create_interaction(
                    {
                        "search_event_id": test_search_event.id,
                        "interaction_type": interaction_type,
                        "instructor_id": test_instructors[0].id,
                    }
                )
        db.commit()

        # Get funnel
        funnel = interaction_repository.get_interaction_funnel(test_search_event.id)

        assert funnel["view"] == 10
        assert funnel["hover"] == 8
        assert funnel["click"] == 5
        assert funnel["view_profile"] == 3
        assert funnel["contact"] == 1
        assert funnel["book"] == 0  # No bookings

    def test_get_time_to_first_click(self, interaction_repository, test_user, db):
        """Test calculating time to first click."""
        # Create search events
        event_ids = []
        for i in range(3):
            event = SearchEvent(
                user_id=test_user.id,
                search_query=f"query {i}",
                search_type="natural_language",
                results_count=10,
                searched_at=datetime.now(timezone.utc),
            )
            db.add(event)
            db.flush()
            event_ids.append(event.id)

        # Create clicks with different times
        times = [2.5, 5.0, 3.5]
        for i, time_to_click in enumerate(times):
            # Create multiple clicks per event, first one should be used
            interaction_repository.create_interaction(
                {
                    "search_event_id": event_ids[i],
                    "interaction_type": "click",
                    "time_to_interaction": time_to_click,
                }
            )
            # Second click (should be ignored)
            interaction_repository.create_interaction(
                {
                    "search_event_id": event_ids[i],
                    "interaction_type": "click",
                    "time_to_interaction": time_to_click + 10,
                }
            )
        db.commit()

        # Get time to first click
        timing_data = interaction_repository.get_time_to_first_click(event_ids)

        assert timing_data["avg_time_seconds"] == 3.67  # (2.5 + 5.0 + 3.5) / 3
        assert timing_data["median_time_seconds"] == 3.5
        assert timing_data["sample_size"] == 3

    def test_get_time_to_first_click_no_clicks(self, interaction_repository):
        """Test time to first click when there are no clicks."""
        from app.core.ulid_helper import generate_ulid

        timing_data = interaction_repository.get_time_to_first_click(
            [generate_ulid(), generate_ulid(), generate_ulid()]
        )

        assert timing_data["avg_time_seconds"] is None
        assert timing_data["median_time_seconds"] is None

    def test_get_popular_instructors_from_clicks(self, interaction_repository, test_search_event, test_instructors, db):
        """Test getting popular instructors based on clicks."""
        # Create clicks for different instructors (use first 4 test instructors)
        instructor_clicks = [
            (test_instructors[0].id, 10),
            (test_instructors[1].id, 8),
            (test_instructors[2].id, 5),
            (test_instructors[3].id, 3),
        ]

        for instructor_id, click_count in instructor_clicks:
            for i in range(click_count):
                interaction_repository.create_interaction(
                    {
                        "search_event_id": test_search_event.id,
                        "interaction_type": "click",
                        "instructor_id": instructor_id,
                        "result_position": (i % 5) + 1,  # Positions 1-5
                    }
                )
        db.commit()

        # Get popular instructors
        popular = interaction_repository.get_popular_instructors_from_clicks(days=7, limit=3)

        assert len(popular) == 3
        assert popular[0]["instructor_id"] == test_instructors[0].id
        assert popular[0]["click_count"] == 10
        assert popular[1]["instructor_id"] == test_instructors[1].id
        assert popular[1]["click_count"] == 8
        assert popular[2]["instructor_id"] == test_instructors[2].id
        assert popular[2]["click_count"] == 5

        # Verify average positions are calculated
        assert all("avg_position" in instructor for instructor in popular)
