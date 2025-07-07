# backend/tests/routes/test_public_simple.py
"""
Simple test to verify public API works after fixes.
"""

from datetime import date, time, timedelta

from sqlalchemy.orm import Session

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

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "instructor_id" in data
    assert data["instructor_id"] == test_instructor.id
    assert "instructor_name" in data
    assert data["instructor_name"] == test_instructor.full_name
    assert "availability_by_date" in data

    # Check today's availability
    today_str = today.isoformat()
    assert today_str in data["availability_by_date"]
    today_data = data["availability_by_date"][today_str]

    assert len(today_data["available_slots"]) == 2
    assert today_data["available_slots"][0]["start_time"] == "09:00"
    assert today_data["available_slots"][0]["end_time"] == "10:00"


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
