from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService as Service


@pytest.fixture(autouse=True)
def _strict(monkeypatch):
    monkeypatch.setenv("STRICT_SCHEMAS", "true")


def test_put_and_get_preferred_places_ok(
    client: TestClient,
    db: Session,
    catalog_data: dict,
    test_instructor,
    auth_headers_instructor: dict,
) -> None:
    payload = {
        "preferred_teaching_locations": [
            {"address": "123 Main St, New York, NY", "label": "Studio"},
            {"address": "456 Broadway, New York, NY", "label": "Home"},
        ],
        "preferred_public_spaces": [
            {"address": "Central Park, New York, NY"},
            {"address": "Bryant Park, New York, NY"},
        ],
    }

    response = client.put("/api/v1/instructors/me", json=payload, headers=auth_headers_instructor)
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["preferred_teaching_locations"] == payload["preferred_teaching_locations"]
    assert data["preferred_public_spaces"] == payload["preferred_public_spaces"]

    follow_up = client.get("/api/v1/instructors/me", headers=auth_headers_instructor)
    assert follow_up.status_code == 200, follow_up.text
    follow_data = follow_up.json()
    assert follow_data["preferred_teaching_locations"] == payload["preferred_teaching_locations"]
    assert follow_data["preferred_public_spaces"] == payload["preferred_public_spaces"]


def test_enforce_max_two_per_kind(
    client: TestClient,
    db: Session,
    catalog_data: dict,
    test_instructor,
    auth_headers_instructor: dict,
) -> None:
    payload = {
        "preferred_teaching_locations": [
            {"address": "11 5th Ave, New York, NY", "label": "Studio"},
            {"address": "12 5th Ave, New York, NY", "label": "Home"},
            {"address": "13 5th Ave, New York, NY", "label": "Office"},
        ]
    }

    response = client.put("/api/v1/instructors/me", json=payload, headers=auth_headers_instructor)
    assert response.status_code == 422
    body = response.json()
    detail = body.get("detail") if isinstance(body, dict) else None
    messages: list[str] = []
    if isinstance(detail, dict):
        msg = detail.get("message")
        if isinstance(msg, str):
            messages.append(msg)
    elif isinstance(detail, list):
        for entry in detail:
            if isinstance(entry, dict):
                msg = entry.get("msg")
                if isinstance(msg, str):
                    messages.append(msg)
    assert any("at most two" in msg.lower() for msg in messages)


def test_dedupe_on_address(
    client: TestClient,
    db: Session,
    catalog_data: dict,
    test_instructor,
    auth_headers_instructor: dict,
) -> None:
    payload = {
        "preferred_public_spaces": [
            {"address": "Central Park West"},
            {"address": " central park west "},
        ]
    }

    response = client.put("/api/v1/instructors/me", json=payload, headers=auth_headers_instructor)
    assert response.status_code == 422
    body = response.json()
    detail = body.get("detail") if isinstance(body, dict) else {}
    message = ""
    if isinstance(detail, dict):
        msg = detail.get("message")
        if isinstance(msg, str):
            message = msg
    elif isinstance(detail, str):
        message = detail
    if not message:
        if isinstance(detail, list) and detail:
            entry = detail[0]
            if isinstance(entry, dict):
                msg = entry.get("msg")
                if isinstance(msg, str):
                    message = msg
    assert "duplicate addresses" in message.lower()


def test_delete_all_preferred_places(
    client: TestClient,
    db: Session,
    catalog_data: dict,
    test_instructor,
    auth_headers_instructor: dict,
) -> None:
    seed_payload = {
        "preferred_teaching_locations": [
            {"address": "123 Main St, New York, NY", "label": "Studio"},
        ],
        "preferred_public_spaces": [
            {"address": "Central Park"},
        ],
    }
    set_resp = client.put("/api/v1/instructors/me", json=seed_payload, headers=auth_headers_instructor)
    assert set_resp.status_code == 200, set_resp.text

    clear_payload = {
        "preferred_teaching_locations": [],
        "preferred_public_spaces": [],
    }
    clear_resp = client.put("/api/v1/instructors/me", json=clear_payload, headers=auth_headers_instructor)
    assert clear_resp.status_code == 200, clear_resp.text
    cleared = clear_resp.json()
    assert cleared["preferred_teaching_locations"] == []
    assert cleared["preferred_public_spaces"] == []

    follow_up = client.get("/api/v1/instructors/me", headers=auth_headers_instructor)
    assert follow_up.status_code == 200
    follow_data = follow_up.json()
    assert follow_data["preferred_teaching_locations"] == []
    assert follow_data["preferred_public_spaces"] == []


def test_cannot_remove_last_teaching_location_when_offers_at_location(
    client: TestClient,
    db: Session,
    catalog_data: dict,
    test_instructor,
    auth_headers_instructor: dict,
) -> None:
    profile = (
        db.query(InstructorProfile)
        .filter(InstructorProfile.user_id == test_instructor.id)
        .first()
    )
    assert profile is not None
    service = (
        db.query(Service)
        .filter(Service.instructor_profile_id == profile.id)
        .order_by(Service.created_at.asc())
        .first()
    )
    assert service is not None
    service.offers_at_location = True
    db.commit()

    seed_payload = {
        "preferred_teaching_locations": [
            {"address": "123 Main St, New York, NY", "label": "Studio"},
        ],
    }
    seed_resp = client.put("/api/v1/instructors/me", json=seed_payload, headers=auth_headers_instructor)
    assert seed_resp.status_code == 200, seed_resp.text

    clear_payload = {
        "preferred_teaching_locations": [],
    }
    clear_resp = client.put(
        "/api/v1/instructors/me",
        json=clear_payload,
        headers=auth_headers_instructor,
    )
    assert clear_resp.status_code == 422, clear_resp.text
    payload = clear_resp.json()
    detail = payload.get("detail") if isinstance(payload, dict) else None
    message = ""
    if isinstance(detail, dict):
        msg = detail.get("message")
        if isinstance(msg, str):
            message = msg
    elif isinstance(detail, str):
        message = detail
    assert "last teaching location" in message.lower()
