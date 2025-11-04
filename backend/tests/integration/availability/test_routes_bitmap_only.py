from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.models import AvailabilityDay, User

pytest_plugins = ("tests.integration.availability.test_week_bitmap_routes",)


def test_week_get_uses_bitmap(
    bitmap_client: TestClient,
    db: Session,
    test_instructor: User,
    auth_headers_instructor: dict,
) -> None:
    week_start = date(2026, 1, 5)
    db.query(AvailabilityDay).filter(AvailabilityDay.instructor_id == test_instructor.id).delete()
    db.commit()

    resp = bitmap_client.get(
        "/instructors/availability/week",
        params={"start_date": week_start.isoformat()},
        headers=auth_headers_instructor,
    )

    assert resp.status_code == 200
    assert resp.headers.get("x-db-table-availability_slots") == "0"


def test_week_post_uses_bitmap(
    bitmap_client: TestClient,
    db: Session,
    test_instructor: User,
    auth_headers_instructor: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.availability_service.AvailabilityService._enqueue_week_save_event",
        lambda *args, **kwargs: None,
    )
    week_start = date(2026, 1, 12)
    db.query(AvailabilityDay).filter(AvailabilityDay.instructor_id == test_instructor.id).delete()
    db.commit()

    payload = {
        "week_start": week_start.isoformat(),
        "clear_existing": True,
        "schedule": [
            {
                "date": week_start.isoformat(),
                "start_time": "09:00:00",
                "end_time": "10:00:00",
            }
        ],
    }

    resp = bitmap_client.post(
        "/instructors/availability/week",
        json=payload,
        headers=auth_headers_instructor,
    )

    assert resp.status_code == 200
    assert resp.headers.get("x-db-table-availability_slots") == "0"
