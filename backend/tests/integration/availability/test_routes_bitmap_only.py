from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.models import AvailabilityDay, User
from app.utils.bitmap_base64 import decode_bitmap_bytes, encode_bitmap_bytes
from app.utils.bitset import bits_from_windows, new_empty_tags, windows_from_bits

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
        "/api/v1/instructors/availability/week",
        params={"start_date": week_start.isoformat()},
        headers=auth_headers_instructor,
    )

    assert resp.status_code == 200
    assert resp.headers.get("x-db-table-availability_slots") == "0"
    body = resp.json()
    assert "days" in body and "version" in body


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
    today = date.today()
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    week_start = today + timedelta(days=days_until_monday)
    db.query(AvailabilityDay).filter(AvailabilityDay.instructor_id == test_instructor.id).delete()
    db.commit()

    payload = {
        "week_start": week_start.isoformat(),
        "clear_existing": True,
        "days": [
            {
                "date": week_start.isoformat(),
                "bits": encode_bitmap_bytes(bits_from_windows([("09:00:00", "10:00:00")])),
                "format_tags": encode_bitmap_bytes(new_empty_tags()),
            }
        ],
    }

    resp = bitmap_client.post(
        "/api/v1/instructors/availability/week",
        json=payload,
        headers=auth_headers_instructor,
    )

    assert resp.status_code == 200
    assert resp.headers.get("x-db-table-availability_slots") == "0"
    follow_up = bitmap_client.get(
        "/api/v1/instructors/availability/week",
        params={"start_date": week_start.isoformat()},
        headers=auth_headers_instructor,
    )
    body = follow_up.json()
    day = next(item for item in body["days"] if item["date"] == week_start.isoformat())
    assert windows_from_bits(decode_bitmap_bytes(day["bits"], 36)) == [("09:00:00", "10:00:00")]
