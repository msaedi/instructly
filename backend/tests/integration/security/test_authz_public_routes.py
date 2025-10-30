from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient
import pytest


@pytest.mark.integration
def test_open_route_allows_anonymous(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200


@pytest.mark.integration
def test_student_badges_endpoint_requires_student_role(
    client: TestClient,
    auth_headers_student,
    auth_headers_instructor,
) -> None:
    unauth_response = client.get("/api/students/badges")
    assert unauth_response.status_code in (401, 403)

    instructor_response = client.get("/api/students/badges", headers=auth_headers_instructor)
    assert instructor_response.status_code == 403

    student_response = client.get("/api/students/badges", headers=auth_headers_student)
    assert student_response.status_code == 200


@pytest.mark.integration
def test_instructor_availability_requires_instructor_role(
    client: TestClient,
    auth_headers_student,
    auth_headers_instructor,
) -> None:
    schedule_date = date.today() + timedelta(days=21)
    payload = {
        "schedule": [
            {
                "date": schedule_date.isoformat(),
                "start_time": "08:00",
                "end_time": "09:00",
            }
        ],
        "clear_existing": False,
    }

    unauth_response = client.post("/instructors/availability/week", json=payload)
    assert unauth_response.status_code in (401, 403)

    student_response = client.post(
        "/instructors/availability/week", json=payload, headers=auth_headers_student
    )
    assert student_response.status_code == 403

    instructor_response = client.post(
        "/instructors/availability/week", json=payload, headers=auth_headers_instructor
    )
    assert instructor_response.status_code == 200
