# backend/tests/routes/test_public_configuration.py
"""
Tests for public API configuration settings.
These tests are dynamic and work with any configuration.
"""

from datetime import date, time, timedelta
from unittest.mock import patch

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.availability import AvailabilitySlot


class TestPublicAPIConfiguration:
    """Test that public API respects configuration settings."""

    def test_respects_configured_day_limit(self, client, db: Session, test_instructor):
        """Test that API respects public_availability_days setting."""
        # Create availability for 30 days
        today = date.today()
        for i in range(30):
            slot = AvailabilitySlot(
                instructor_id=test_instructor.id,
                specific_date=today + timedelta(days=i),
                start_time=time(9, 0),
                end_time=time(10, 0),
            )
            db.add(slot)
        db.commit()

        # Request 30 days
        response = client.get(
            f"/api/public/instructors/{test_instructor.id}/availability",
            params={"start_date": today.isoformat(), "end_date": (today + timedelta(days=29)).isoformat()},
        )

        assert response.status_code == 200
        result = response.json()

        # Check based on current detail level
        if settings.public_availability_detail_level == "full":
            # Full detail has availability_by_date
            expected_days = min(30, settings.public_availability_days)
            actual_days = len(result["availability_by_date"])
            # Allow for inclusive date range
            assert actual_days <= expected_days + 1
        elif settings.public_availability_detail_level == "summary":
            # Summary has availability_summary
            expected_days = min(30, settings.public_availability_days)
            actual_days = len(result["availability_summary"])
            assert actual_days <= expected_days + 1
        else:  # minimal
            # Minimal doesn't have day-by-day data
            assert "has_availability" in result
            assert result["has_availability"] is True

    @patch("app.core.config.settings.public_availability_detail_level", "minimal")
    def test_minimal_detail_level(self, client, db: Session, test_instructor):
        """Test minimal detail level returns only basic info."""
        # Create some availability
        today = date.today()
        slot = AvailabilitySlot(
            instructor_id=test_instructor.id, specific_date=today, start_time=time(9, 0), end_time=time(10, 0)
        )
        db.add(slot)
        db.commit()

        response = client.get(
            f"/api/public/instructors/{test_instructor.id}/availability", params={"start_date": today.isoformat()}
        )

        assert response.status_code == 200
        result = response.json()

        # Minimal response should have these fields
        assert "instructor_id" in result
        assert "instructor_first_name" in result or "instructor_last_initial" in result
        assert "has_availability" in result or "availability_by_date" in result
        # Check if we have availability (either format is valid)
        if "has_availability" in result:
            assert result["has_availability"] is True
        assert "earliest_available_date" in result

        # Should NOT have detailed slots
        assert "availability_by_date" not in result
        assert "availability_summary" not in result

    @patch("app.core.config.settings.public_availability_detail_level", "summary")
    def test_summary_detail_level(self, client, db: Session, test_instructor):
        """Test summary detail level returns time ranges."""
        # Create morning and evening slots
        today = date.today()
        slots = [
            AvailabilitySlot(
                instructor_id=test_instructor.id,
                specific_date=today,
                start_time=time(9, 0),  # Morning
                end_time=time(11, 0),
            ),
            AvailabilitySlot(
                instructor_id=test_instructor.id,
                specific_date=today,
                start_time=time(18, 0),  # Evening
                end_time=time(20, 0),
            ),
        ]
        for slot in slots:
            db.add(slot)
        db.commit()

        response = client.get(
            f"/api/public/instructors/{test_instructor.id}/availability", params={"start_date": today.isoformat()}
        )

        assert response.status_code == 200
        result = response.json()

        # Summary response should have these fields
        assert "availability_summary" in result
        assert "detail_level" in result
        assert result["detail_level"] == "summary"

        # Check summary data
        today_str = today.isoformat()
        assert today_str in result["availability_summary"]

        summary = result["availability_summary"][today_str]
        assert summary["morning_available"] is True
        assert summary["afternoon_available"] is False
        assert summary["evening_available"] is True
        assert summary["total_hours"] == 4.0  # 2 + 2 hours

    @patch("app.core.config.settings.public_availability_show_instructor_name", False)
    def test_hide_instructor_name(self, client, test_instructor):
        """Test that instructor name can be hidden."""
        response = client.get(
            f"/api/public/instructors/{test_instructor.id}/availability",
            params={"start_date": date.today().isoformat()},
        )

        assert response.status_code == 200
        result = response.json()

        # When configured to hide names, should not include name fields
        assert "instructor_first_name" not in result or result["instructor_first_name"] is None
        assert "instructor_last_initial" not in result or result["instructor_last_initial"] is None

    def test_cache_ttl_configuration(self, client, test_instructor, monkeypatch, db: Session):
        """Test that cache TTL uses configured value."""
        from datetime import time as datetime_time

        from app.models.availability import AvailabilitySlot

        # Create some availability so there's data to cache
        slot = AvailabilitySlot(
            instructor_id=test_instructor.id,
            specific_date=date.today(),
            start_time=datetime_time(9, 0),
            end_time=datetime_time(10, 0),
        )
        db.add(slot)
        db.commit()

        cache_ttl_used = None

        def mock_set(self, key, value, ttl=None):
            nonlocal cache_ttl_used
            cache_ttl_used = ttl
            return True

        # Mock the cache service's set method
        from app.services.cache_service import CacheService

        original_set = CacheService.set
        monkeypatch.setattr(CacheService, "set", mock_set)

        # Make request - this should trigger caching with TTL
        response = client.get(
            f"/api/public/instructors/{test_instructor.id}/availability",
            params={"start_date": date.today().isoformat()},
        )

        assert response.status_code == 200

        # Verify configured TTL was used (300 seconds = 5 minutes)
        assert cache_ttl_used == settings.public_availability_cache_ttl
        assert cache_ttl_used == 300  # Explicitly check for 5 minutes

    def test_default_date_range_uses_configured_days(self, client, test_instructor, db: Session):
        """Test that default end date uses configured days."""
        # Create availability for many days
        today = date.today()
        for i in range(settings.public_availability_days + 5):
            slot = AvailabilitySlot(
                instructor_id=test_instructor.id,
                specific_date=today + timedelta(days=i),
                start_time=time(9, 0),
                end_time=time(10, 0),
            )
            db.add(slot)
        db.commit()

        # Don't provide end_date
        response = client.get(
            f"/api/public/instructors/{test_instructor.id}/availability", params={"start_date": today.isoformat()}
        )

        assert response.status_code == 200
        result = response.json()

        # Check based on detail level
        if settings.public_availability_detail_level == "full":
            days_returned = len(result["availability_by_date"])
            assert days_returned == settings.public_availability_days
        elif settings.public_availability_detail_level == "summary":
            days_returned = len(result["availability_summary"])
            assert days_returned <= settings.public_availability_days
        else:  # minimal
            # Minimal doesn't return day-by-day data
            assert "has_availability" in result

    def test_requested_range_limited_by_config(self, client, test_instructor, db: Session):
        """Test that requested range is limited by configuration."""
        # Create availability for many days
        today = date.today()
        for i in range(90):
            slot = AvailabilitySlot(
                instructor_id=test_instructor.id,
                specific_date=today + timedelta(days=i),
                start_time=time(9, 0),
                end_time=time(10, 0),
            )
            db.add(slot)
        db.commit()

        # Request 90 days
        response = client.get(
            f"/api/public/instructors/{test_instructor.id}/availability",
            params={"start_date": today.isoformat(), "end_date": (today + timedelta(days=89)).isoformat()},
        )

        assert response.status_code == 200
        result = response.json()

        # Check based on detail level
        if settings.public_availability_detail_level == "full":
            days_returned = len(result["availability_by_date"])
            assert days_returned == settings.public_availability_days
        elif settings.public_availability_detail_level == "summary":
            days_returned = len(result["availability_summary"])
            assert days_returned <= settings.public_availability_days
        else:  # minimal
            # Minimal doesn't return day-by-day data
            assert "has_availability" in result

    @patch("app.core.config.settings.public_availability_detail_level", "full")
    def test_full_detail_level(self, client, db: Session, test_instructor):
        """Test full detail level returns all slot details."""
        # Create some availability
        today = date.today()
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

        response = client.get(
            f"/api/public/instructors/{test_instructor.id}/availability", params={"start_date": today.isoformat()}
        )

        assert response.status_code == 200
        result = response.json()

        # Full response should have these fields
        assert "availability_by_date" in result
        assert "total_available_slots" in result
        assert "earliest_available_date" in result

        # Check detailed slot data
        today_str = today.isoformat()
        assert today_str in result["availability_by_date"]

        slots_data = result["availability_by_date"][today_str]["available_slots"]
        assert len(slots_data) == 2
        assert slots_data[0]["start_time"] == "09:00"
        assert slots_data[0]["end_time"] == "10:00"
