"""Comprehensive tests for TimezoneService."""

from datetime import date, datetime, time, timedelta, timezone

import pytest

from app.services.timezone_service import TimezoneService


class TestLocalToUtc:
    """Test local_to_utc conversion."""

    def test_est_to_utc_winter(self):
        """11:00 AM EST (winter) = 16:00 UTC."""
        result = TimezoneService.local_to_utc(
            booking_date=date(2025, 12, 25),
            start_time=time(11, 0),
            timezone_str="America/New_York",
        )
        assert result.hour == 16
        assert result.minute == 0
        assert result.tzinfo == timezone.utc

    def test_edt_to_utc_summer(self):
        """11:00 AM EDT (summer) = 15:00 UTC."""
        result = TimezoneService.local_to_utc(
            booking_date=date(2025, 6, 15),
            start_time=time(11, 0),
            timezone_str="America/New_York",
        )
        assert result.hour == 15
        assert result.minute == 0

    def test_pst_to_utc(self):
        """11:00 AM PST = 19:00 UTC."""
        result = TimezoneService.local_to_utc(
            booking_date=date(2025, 12, 25),
            start_time=time(11, 0),
            timezone_str="America/Los_Angeles",
        )
        assert result.hour == 19

    def test_dst_spring_forward_gap_raises(self):
        """Time during spring forward gap raises ValueError."""
        with pytest.raises(ValueError, match="does not exist"):
            TimezoneService.local_to_utc(
                booking_date=date(2025, 3, 9),
                start_time=time(2, 30),
                timezone_str="America/New_York",
            )

    def test_dst_fall_back_uses_first_occurrence(self):
        """Time during fall back (exists twice) uses first occurrence (DST)."""
        result = TimezoneService.local_to_utc(
            booking_date=date(2025, 11, 2),
            start_time=time(1, 30),
            timezone_str="America/New_York",
        )
        assert result.hour == 5
        assert result.minute == 30

    def test_booking_preserves_wall_clock_across_dst(self):
        """
        Booking for 2 PM on March 15 (after DST) should be 2 PM EDT.

        This tests that we use the DST rules for the event date, not the booking date.
        """
        result = TimezoneService.local_to_utc(
            booking_date=date(2025, 3, 15),
            start_time=time(14, 0),
            timezone_str="America/New_York",
        )
        assert result.hour == 18

    def test_invalid_timezone_falls_back_to_default(self):
        """Invalid timezone falls back to America/New_York."""
        result = TimezoneService.local_to_utc(
            booking_date=date(2025, 12, 25),
            start_time=time(11, 0),
            timezone_str="Invalid/Timezone",
        )
        assert result.hour == 16


class TestUtcToLocal:
    """Test utc_to_local conversion."""

    def test_utc_to_est(self):
        """16:00 UTC = 11:00 AM EST."""
        utc_dt = datetime(2025, 12, 25, 16, 0, tzinfo=timezone.utc)
        result = TimezoneService.utc_to_local(utc_dt, "America/New_York")
        assert result.hour == 11

    def test_utc_to_pst(self):
        """16:00 UTC = 8:00 AM PST."""
        utc_dt = datetime(2025, 12, 25, 16, 0, tzinfo=timezone.utc)
        result = TimezoneService.utc_to_local(utc_dt, "America/Los_Angeles")
        assert result.hour == 8

    def test_utc_to_edt_summer(self):
        """15:00 UTC = 11:00 AM EDT (summer)."""
        utc_dt = datetime(2025, 6, 15, 15, 0, tzinfo=timezone.utc)
        result = TimezoneService.utc_to_local(utc_dt, "America/New_York")
        assert result.hour == 11

    def test_naive_utc_input_handled(self):
        """Naive datetime input is treated as UTC."""
        naive_dt = datetime(2025, 12, 25, 16, 0)
        result = TimezoneService.utc_to_local(naive_dt, "America/New_York")
        assert result.hour == 11


class TestValidateTimeExists:
    """Test DST validation."""

    def test_normal_time_valid(self):
        """Normal time is valid."""
        is_valid, error = TimezoneService.validate_time_exists(
            date(2025, 6, 15), time(14, 0), "America/New_York"
        )
        assert is_valid is True
        assert error is None

    def test_spring_forward_gap_invalid(self):
        """Time during spring forward gap is invalid."""
        is_valid, error = TimezoneService.validate_time_exists(
            date(2025, 3, 9), time(2, 30), "America/New_York"
        )
        assert is_valid is False
        assert "does not exist" in error

    def test_fall_back_overlap_valid(self):
        """Time during fall back (exists twice) is valid."""
        is_valid, error = TimezoneService.validate_time_exists(
            date(2025, 11, 2), time(1, 30), "America/New_York"
        )
        assert is_valid is True
        assert error is None

    def test_time_just_before_gap_valid(self):
        """1:59 AM on spring forward day is valid."""
        is_valid, error = TimezoneService.validate_time_exists(
            date(2025, 3, 9), time(1, 59), "America/New_York"
        )
        assert is_valid is True

    def test_time_just_after_gap_valid(self):
        """3:00 AM on spring forward day is valid."""
        is_valid, error = TimezoneService.validate_time_exists(
            date(2025, 3, 9), time(3, 0), "America/New_York"
        )
        assert is_valid is True


class TestHoursUntil:
    """Test hours_until calculation."""

    def test_future_booking(self):
        """Future booking returns positive hours."""
        future = datetime.now(timezone.utc) + timedelta(hours=5)
        hours = TimezoneService.hours_until(future)
        assert 4.9 < hours < 5.1

    def test_past_booking(self):
        """Past booking returns negative hours."""
        past = datetime.now(timezone.utc) - timedelta(hours=2)
        hours = TimezoneService.hours_until(past)
        assert -2.1 < hours < -1.9

    def test_exactly_now(self):
        """Booking right now returns ~0."""
        now = datetime.now(timezone.utc)
        hours = TimezoneService.hours_until(now)
        assert -0.01 < hours < 0.01


class TestIsPast:
    """Test is_past helper."""

    def test_future_not_past(self):
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        assert TimezoneService.is_past(future) is False

    def test_past_is_past(self):
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        assert TimezoneService.is_past(past) is True


class TestGetLessonTimezone:
    """Test get_lesson_timezone rules."""

    def test_in_person_uses_instructor(self):
        """In-person lesson uses instructor timezone."""
        result = TimezoneService.get_lesson_timezone(
            instructor_timezone="America/New_York", is_online=False
        )
        assert result == "America/New_York"

    def test_online_uses_instructor(self):
        """Online lesson uses instructor timezone."""
        result = TimezoneService.get_lesson_timezone(
            instructor_timezone="America/Los_Angeles", is_online=True
        )
        assert result == "America/Los_Angeles"

    def test_none_timezone_uses_default(self):
        """None timezone falls back to default."""
        result = TimezoneService.get_lesson_timezone(
            instructor_timezone=None, is_online=False
        )
        assert result == "America/New_York"


class TestFormatForDisplay:
    """Test display formatting."""

    def test_format_with_tz_abbrev(self):
        utc_dt = datetime(2025, 12, 25, 16, 0, tzinfo=timezone.utc)
        result = TimezoneService.format_for_display(
            utc_dt, "America/New_York", include_tz_abbrev=True
        )
        assert "Dec 25, 2025" in result
        assert "11:00 AM" in result
        assert "EST" in result

    def test_format_without_tz_abbrev(self):
        utc_dt = datetime(2025, 12, 25, 16, 0, tzinfo=timezone.utc)
        result = TimezoneService.format_for_display(
            utc_dt, "America/New_York", include_tz_abbrev=False
        )
        assert "Dec 25, 2025" in result
        assert "11:00 AM" in result
        assert "EST" not in result


class TestCrossTimezoneScenarios:
    """Test real-world cross-timezone scenarios."""

    def test_nyc_instructor_la_student_online(self):
        """
        NYC instructor sets 2 PM availability.
        LA student should see 11 AM.
        """
        booking_start_utc = TimezoneService.local_to_utc(
            booking_date=date(2025, 12, 25),
            start_time=time(14, 0),
            timezone_str="America/New_York",
        )
        assert booking_start_utc.hour == 19

        la_local = TimezoneService.utc_to_local(booking_start_utc, "America/Los_Angeles")
        assert la_local.hour == 11

    def test_booking_made_before_dst_for_after_dst(self):
        """
        Student books on March 1 (before DST) for March 15 (after DST).
        The 2 PM wall clock should stay at 2 PM local.
        """
        booking_start_utc = TimezoneService.local_to_utc(
            booking_date=date(2025, 3, 15),
            start_time=time(14, 0),
            timezone_str="America/New_York",
        )

        local_time = TimezoneService.utc_to_local(booking_start_utc, "America/New_York")
        assert local_time.hour == 14
        assert local_time.minute == 0
