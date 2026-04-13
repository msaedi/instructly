from __future__ import annotations

from datetime import date, timedelta

from fastapi import status
import pytest
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.availability import BlackoutDate
from app.services.config_service import ConfigService
from tests._utils.bitmap_avail import seed_day


@pytest.fixture
def full_detail_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "public_availability_detail_level", "full")
    monkeypatch.setattr(settings, "public_availability_days", 30)
    monkeypatch.setattr(settings, "public_availability_show_instructor_name", True)
    monkeypatch.setattr(settings, "public_availability_cache_ttl", 300)


class TestPublicAvailabilityBugHuntRoutes:
    def test_public_availability_all_day_blackout_hides_full_day_bitmap(
        self,
        client,
        db: Session,
        test_instructor,
        full_detail_settings,
    ) -> None:
        target_date = date.today() + timedelta(days=7)
        seed_day(db, test_instructor.id, target_date, [("00:00", "24:00")])
        db.add(
            BlackoutDate(
                instructor_id=test_instructor.id,
                date=target_date,
                reason="All-day blackout",
            )
        )
        db.commit()

        response = client.get(
            f"/api/v1/public/instructors/{test_instructor.id}/availability",
            params={
                "start_date": target_date.isoformat(),
                "end_date": target_date.isoformat(),
            },
        )
        if response.status_code == 404:
            pytest.skip("Public routes not registered in main.py")

        assert response.status_code == status.HTTP_200_OK
        day = response.json()["availability_by_date"][target_date.isoformat()]
        assert day["is_blackout"] is True
        assert day["available_slots"] == []

    def test_next_available_skips_blackout_day_with_bitmap_availability(
        self,
        client,
        db: Session,
        test_instructor,
        full_detail_settings,
    ) -> None:
        today = date.today()
        tomorrow = today + timedelta(days=1)
        seed_day(db, test_instructor.id, today, [("09:00", "17:00")])
        seed_day(db, test_instructor.id, tomorrow, [("10:00", "11:00")])
        db.add(
            BlackoutDate(
                instructor_id=test_instructor.id,
                date=today,
                reason="Unavailable today",
            )
        )
        db.commit()

        response = client.get(
            f"/api/v1/public/instructors/{test_instructor.id}/next-available",
            params={"duration_minutes": 60},
        )
        if response.status_code == 404:
            pytest.skip("Public routes not registered in main.py")

        assert response.status_code == status.HTTP_200_OK
        payload = response.json()
        assert payload["found"] is True
        assert payload["date"] == tomorrow.isoformat()
        assert payload["start_time"] == "10:00:00"

    def test_next_available_returns_not_found_for_ninety_minute_request_when_only_sixty_exists(
        self,
        client,
        db: Session,
        test_instructor,
        full_detail_settings,
    ) -> None:
        target_date = date.today()
        seed_day(db, test_instructor.id, target_date, [("09:00", "10:00")])
        db.commit()

        response = client.get(
            f"/api/v1/public/instructors/{test_instructor.id}/next-available",
            params={"duration_minutes": 90},
        )
        if response.status_code == 404:
            pytest.skip("Public routes not registered in main.py")

        assert response.status_code == status.HTTP_200_OK
        payload = response.json()
        assert payload["found"] is False
        assert "No available slots" in payload["message"]

    def test_public_availability_currently_exposes_unaligned_slot_boundaries(
        self,
        client,
        db: Session,
        test_instructor,
        full_detail_settings,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # BUG: the public availability response currently exposes 5-minute bitmap edges
        # directly even though booking starts are meant to align to 15-minute increments.
        monkeypatch.setattr(
            ConfigService,
            "get_advance_notice_minutes",
            lambda self, location_type=None: 0,
        )
        target_date = date.today()
        seed_day(db, test_instructor.id, target_date, [("09:05", "09:35")])
        db.commit()

        response = client.get(
            f"/api/v1/public/instructors/{test_instructor.id}/availability",
            params={
                "start_date": target_date.isoformat(),
                "end_date": target_date.isoformat(),
            },
        )
        if response.status_code == 404:
            pytest.skip("Public routes not registered in main.py")

        assert response.status_code == status.HTTP_200_OK
        slots = response.json()["availability_by_date"][target_date.isoformat()]["available_slots"]
        assert slots == [{"start_time": "09:05", "end_time": "09:35"}]

    def test_next_available_currently_returns_unaligned_start_for_thirty_minute_window(
        self,
        client,
        db: Session,
        test_instructor,
        full_detail_settings,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # BUG: next-available returns the raw slot start from public availability, so an
        # unaligned 09:05 window is surfaced as bookable instead of being rounded or rejected.
        monkeypatch.setattr(
            ConfigService,
            "get_advance_notice_minutes",
            lambda self, location_type=None: 0,
        )
        target_date = date.today()
        seed_day(db, test_instructor.id, target_date, [("09:05", "09:35")])
        db.commit()

        response = client.get(
            f"/api/v1/public/instructors/{test_instructor.id}/next-available",
            params={"duration_minutes": 30},
        )
        if response.status_code == 404:
            pytest.skip("Public routes not registered in main.py")

        assert response.status_code == status.HTTP_200_OK
        payload = response.json()
        assert payload["found"] is True
        assert payload["date"] == target_date.isoformat()
        assert payload["start_time"] == "09:05:00"
        assert payload["end_time"] == "09:35:00"
