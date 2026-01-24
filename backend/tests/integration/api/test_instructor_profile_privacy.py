from __future__ import annotations

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.models.instructor import InstructorPreferredPlace


def test_public_profile_returns_approx_teaching_location_only(
    client: TestClient,
    db: Session,
    test_instructor,
    auth_headers_student: dict,
) -> None:
    place = InstructorPreferredPlace(
        instructor_id=test_instructor.id,
        kind="teaching_location",
        address="225 Cherry Street, New York, NY 10002",
        label="Studio",
        position=0,
        lat=40.7128,
        lng=-74.0060,
        approx_lat=40.7138,
        approx_lng=-74.0050,
        neighborhood="Lower East Side, Manhattan",
    )
    db.add(place)
    db.commit()

    response = client.get(f"/api/v1/instructors/{test_instructor.id}", headers=auth_headers_student)
    assert response.status_code == 200

    data = response.json()
    locations = data.get("preferred_teaching_locations", [])
    assert locations, "Expected preferred teaching locations on public profile response"

    location = locations[0]
    assert location.get("approx_lat") == pytest.approx(40.7138)
    assert location.get("approx_lng") == pytest.approx(-74.0050)
    assert location.get("neighborhood") == "Lower East Side, Manhattan"
    assert "address" not in location
