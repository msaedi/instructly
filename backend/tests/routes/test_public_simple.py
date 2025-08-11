# backend/tests/routes/test_public_simple.py
"""
Simple test to verify public API works after fixes.
These tests adapt to current configuration settings.
"""

from datetime import date, time, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.availability import AvailabilitySlot


def test_public_availability_basic(client, db: Session, test_instructor):
    """Test basic public availability endpoint."""
    # Create some availability for today
    today = date.today()

    # Add slots
    slots = [
        AvailabilitySlot(
            instructor_id=test_instructor.id, specific_date=today, start_time=time(9, 0), end_time=time(10, 0)
        ),
        AvailabilitySlot(
            instructor_id=test_instructor.id, specific_date=today, start_time=time(14, 0), end_time=time(15, 0)
        ),
    ]

    for slot in slots:
        db.add(slot)
    db.commit()

    # Test the public endpoint
    response = client.get(
        f"/api/public/instructors/{test_instructor.id}/availability", params={"start_date": today.isoformat()}
    )

    print(f"\nResponse status: {response.status_code}")
    print(f"Response body: {response.json()}")
    print(f"Current detail level: {settings.public_availability_detail_level}")

    assert response.status_code == 200
    data = response.json()

    # Verify common fields that exist in all detail levels
    assert "instructor_id" in data
    assert data["instructor_id"] == test_instructor.id
    assert "instructor_name" in data

    # Check based on configured detail level
    if settings.public_availability_detail_level == "full":
        # Full detail level checks
        assert data["instructor_name"] == test_instructor.first_name  # Clean Break: first name only in public contexts
        assert "availability_by_date" in data

        # Check today's availability
        today_str = today.isoformat()
        assert today_str in data["availability_by_date"]
        today_data = data["availability_by_date"][today_str]

        assert len(today_data["available_slots"]) == 2
        assert today_data["available_slots"][0]["start_time"] == "09:00"
        assert today_data["available_slots"][0]["end_time"] == "10:00"
        assert today_data["available_slots"][1]["start_time"] == "14:00"
        assert today_data["available_slots"][1]["end_time"] == "15:00"

    elif settings.public_availability_detail_level == "summary":
        # Summary detail level checks
        assert "availability_summary" in data
        assert "detail_level" in data
        assert data["detail_level"] == "summary"

        today_str = today.isoformat()
        assert today_str in data["availability_summary"]

        summary = data["availability_summary"][today_str]
        assert summary["morning_available"] is True  # 9-10am slot
        assert summary["afternoon_available"] is True  # 2-3pm slot
        assert summary["evening_available"] is False
        assert summary["total_hours"] == 2.0  # 1 + 1 hours

    else:  # minimal
        # Minimal detail level checks
        assert "has_availability" in data
        assert data["has_availability"] is True
        assert "earliest_available_date" in data
        assert data["earliest_available_date"] == today.isoformat()


def test_public_availability_instructor_not_found(client):
    """Test 404 when instructor doesn't exist."""
    response = client.get("/api/public/instructors/99999/availability", params={"start_date": date.today().isoformat()})

    assert response.status_code == 404
    assert "Instructor not found" in response.json()["detail"]


def test_next_available_basic(client, db: Session, test_instructor):
    """Test next available slot endpoint."""
    # Create availability for tomorrow
    tomorrow = date.today() + timedelta(days=1)

    slot = AvailabilitySlot(
        instructor_id=test_instructor.id,
        specific_date=tomorrow,
        start_time=time(9, 0),
        end_time=time(11, 0),  # 2 hour slot
    )
    db.add(slot)
    db.commit()

    # Find next available
    response = client.get(
        f"/api/public/instructors/{test_instructor.id}/next-available", params={"duration_minutes": 60}
    )

    print(f"\nNext available response: {response.json()}")

    assert response.status_code == 200
    data = response.json()

    assert data["found"] is True
    assert data["date"] == tomorrow.isoformat()
    assert data["start_time"] == "09:00:00"
    assert data["duration_minutes"] == 60


def test_public_availability_no_slots(client, test_instructor):
    """Test response when instructor has no availability."""
    # Don't create any slots

    response = client.get(
        f"/api/public/instructors/{test_instructor.id}/availability", params={"start_date": date.today().isoformat()}
    )

    assert response.status_code == 200
    data = response.json()

    # Check based on detail level
    if settings.public_availability_detail_level == "full":
        # Should have empty availability_by_date
        assert "availability_by_date" in data
        assert len(data["availability_by_date"]) == settings.public_availability_days
        # Each day should have no slots
        for day_data in data["availability_by_date"].values():
            assert len(day_data["available_slots"]) == 0
            assert day_data["is_blackout"] is False
    elif settings.public_availability_detail_level == "summary":
        # Should have empty or no summary
        assert "availability_summary" in data
        assert len(data["availability_summary"]) == 0  # No days with availability
    else:  # minimal
        # Should show no availability
        assert "has_availability" in data
        assert data["has_availability"] is False
        assert data["earliest_available_date"] is None
