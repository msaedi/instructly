"""Tests for app/utils/business_days.py — coverage gaps L23, L90, L93."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.utils.business_days import (
    _nth_weekday,
    add_us_business_days,
    us_federal_holidays,
)


@pytest.mark.unit
class TestNthWeekdayCoverage:
    """Cover L23: n <= 0 raises ValueError."""

    def test_n_zero_raises(self) -> None:
        """L23: n=0 raises ValueError."""
        with pytest.raises(ValueError, match="n must be positive"):
            _nth_weekday(2025, 1, 0, 0)

    def test_n_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="n must be positive"):
            _nth_weekday(2025, 1, 0, -1)

    def test_nth_weekday_valid(self) -> None:
        """3rd Monday of January 2025 = Jan 20."""
        result = _nth_weekday(2025, 1, 0, 3)  # Monday=0
        assert result == date(2025, 1, 20)


@pytest.mark.unit
class TestAddUsBusinessDaysCoverage:
    """Cover L90 (n_days=0) and L93 (holidays is None)."""

    def test_n_days_zero_returns_start(self) -> None:
        """L89-90: n_days=0 returns start_dt immediately."""
        start = datetime(2025, 7, 1, 10, 0, tzinfo=timezone.utc)
        holidays = us_federal_holidays(2025)
        result = add_us_business_days(start, 0, holidays)
        assert result == start

    def test_holidays_none_raises(self) -> None:
        """L92-93: holidays=None raises ValueError."""
        start = datetime(2025, 7, 1, 10, 0, tzinfo=timezone.utc)
        with pytest.raises(ValueError, match="holidays set must be provided"):
            add_us_business_days(start, 1, None)  # type: ignore[arg-type]

    def test_negative_days_raises(self) -> None:
        """L86-87: negative n_days raises ValueError."""
        start = datetime(2025, 7, 1, 10, 0, tzinfo=timezone.utc)
        holidays = us_federal_holidays(2025)
        with pytest.raises(ValueError, match="n_days must be non-negative"):
            add_us_business_days(start, -1, holidays)

    def test_naive_datetime_raises(self) -> None:
        """Timezone-unaware datetime raises."""
        start = datetime(2025, 7, 1, 10, 0)
        holidays = us_federal_holidays(2025)
        with pytest.raises(ValueError, match="timezone-aware"):
            add_us_business_days(start, 1, holidays)

    def test_skip_weekend(self) -> None:
        """Friday + 1 business day = Monday."""
        # 2025-07-04 is Friday (also July 4th holiday)
        # Use a non-holiday Friday: 2025-07-11
        start = datetime(2025, 7, 11, 10, 0, tzinfo=timezone.utc)
        holidays = us_federal_holidays(2025)
        result = add_us_business_days(start, 1, holidays)
        assert result.weekday() == 0  # Monday
        assert result.date() == date(2025, 7, 14)

    def test_skip_holiday(self) -> None:
        """Skip July 4th holiday (Friday in 2025)."""
        start = datetime(2025, 7, 3, 10, 0, tzinfo=timezone.utc)  # Thursday
        holidays = us_federal_holidays(2025)
        result = add_us_business_days(start, 1, holidays)
        # July 4 is Friday (holiday), so next business day is Monday July 7
        assert result.date() == date(2025, 7, 7)

    def test_year_below_1900_raises(self) -> None:
        with pytest.raises(ValueError, match="year must be >= 1900"):
            us_federal_holidays(1899)

    def test_holiday_on_saturday_observed_friday(self) -> None:
        """When a holiday falls on Saturday, the observed day is Friday."""
        # July 4, 2026 is Saturday
        holidays = us_federal_holidays(2026)
        assert date(2026, 7, 3) in holidays  # Observed Friday

    def test_holiday_on_sunday_observed_monday(self) -> None:
        """When a holiday falls on Sunday, the observed day is Monday."""
        # July 4, 2021 is Sunday
        holidays = us_federal_holidays(2021)
        assert date(2021, 7, 5) in holidays  # Observed Monday
