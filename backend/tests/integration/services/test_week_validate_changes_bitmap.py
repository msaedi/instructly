"""Test /week/validate-changes endpoint with bitmap storage."""

from datetime import date, timedelta

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.models.user import User


@pytest.mark.asyncio
async def test_validate_changes_bitmap_smoke(
    db: Session, client: TestClient, test_instructor: User, auth_headers_instructor: dict
):
    """Test that /week/validate-changes works with bitmap storage."""
    # Seed a week with one window
    monday = date.today() + timedelta(days=(7 - date.today().weekday()) % 7)
    if monday <= date.today():
        monday = monday + timedelta(days=7)  # Ensure it's a future Monday

    # Create initial availability
    week_payload = {
        "week_start": monday.isoformat(),
        "clear_existing": True,
        "schedule": [
            {
                "date": monday.isoformat(),
                "start_time": "09:00:00",
                "end_time": "10:00:00",
            }
        ],
    }

    create_resp = client.post(
        "/instructors/availability/week",
        json=week_payload,
        headers=auth_headers_instructor,
    )
    assert create_resp.status_code in (200, 201), f"Failed to seed availability: {create_resp.text}"

    # Now validate an incoming change (e.g., add one more window)
    change = {
        "week_start": monday.isoformat(),
        "current_week": {
            monday.isoformat(): [
                {"start_time": "09:00:00", "end_time": "10:00:00"},
                {"start_time": "14:00:00", "end_time": "15:00:00"},
            ]
        },
        "saved_week": {
            monday.isoformat(): [
                {"start_time": "09:00:00", "end_time": "10:00:00"},
            ]
        },
    }

    r = client.post(
        "/instructors/availability/week/validate-changes",
        json=change,
        headers=auth_headers_instructor,
    )

    assert r.status_code == 200, f"Validation failed: {r.status_code} {r.text}"
    body = r.json()

    # Check that we have some indication of changes
    assert "valid" in body
    assert "summary" in body
    assert "details" in body

    # The validation should detect the new window being added
    assert body["valid"] is True or body["summary"]["invalid_operations"] == 0
