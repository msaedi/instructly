# backend/tests/unit/services/test_get_affected_weeks_edge_cases.py
"""
Edge case tests for week boundary calculations in WeekOperationService.

This test suite was created after discovering a bug in _get_affected_weeks
where iterating with +7 days from an arbitrary start date could skip weeks
when the range spanned week boundaries.

The fix ensures we advance to the next Monday instead of just +7 days.
"""

from datetime import date, timedelta
from unittest.mock import Mock, patch

import pytest

from app.services.week_operation_service import WeekOperationService


class TestGetAffectedWeeksEdgeCases:
    """Test edge cases for week boundary calculations."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return Mock()

    @pytest.fixture
    def service(self, mock_db):
        """Create a WeekOperationService with mocked dependencies."""
        with patch.object(WeekOperationService, '__init__', lambda x, db: None):
            svc = WeekOperationService.__new__(WeekOperationService)
            svc.db = mock_db
            return svc

    def test_range_spanning_two_weeks_starting_thursday(self, service):
        """The exact case that exposed the bug - Thursday to Wednesday spans two weeks."""
        # Thursday Jan 29 to Wednesday Feb 4 spans two weeks
        start = date(2026, 1, 29)  # Thursday
        end = date(2026, 2, 4)     # Wednesday

        weeks = service._get_affected_weeks(start, end)

        assert len(weeks) == 2
        assert date(2026, 1, 26) in weeks  # Week of Jan 26 (Monday)
        assert date(2026, 2, 2) in weeks   # Week of Feb 2 (Monday)

    def test_range_within_single_week(self, service):
        """Range entirely within one week."""
        start = date(2026, 1, 27)  # Tuesday
        end = date(2026, 1, 29)    # Thursday

        weeks = service._get_affected_weeks(start, end)

        assert len(weeks) == 1
        assert date(2026, 1, 26) in weeks

    def test_range_spanning_month_boundary(self, service):
        """Range that crosses month boundary."""
        start = date(2026, 1, 30)  # Friday
        end = date(2026, 2, 3)     # Tuesday

        weeks = service._get_affected_weeks(start, end)

        assert len(weeks) == 2
        assert date(2026, 1, 26) in weeks
        assert date(2026, 2, 2) in weeks

    def test_range_spanning_year_boundary(self, service):
        """Range that crosses year boundary."""
        start = date(2025, 12, 29)  # Monday
        end = date(2026, 1, 4)      # Sunday

        weeks = service._get_affected_weeks(start, end)

        # Dec 29 2025 is Monday, so that's one week
        # Jan 4 2026 is Sunday, which is still in the week of Dec 29
        # Actually Dec 29 + 6 = Jan 4, so this is one week
        assert len(weeks) == 1
        assert date(2025, 12, 29) in weeks

    def test_range_spanning_year_boundary_into_next_week(self, service):
        """Range that crosses year boundary and extends into next week."""
        start = date(2025, 12, 29)  # Monday
        end = date(2026, 1, 5)      # Monday (next week)

        weeks = service._get_affected_weeks(start, end)

        assert len(weeks) == 2
        assert date(2025, 12, 29) in weeks
        assert date(2026, 1, 5) in weeks

    def test_single_day_range(self, service):
        """Start and end are the same day."""
        day = date(2026, 1, 29)  # Thursday

        weeks = service._get_affected_weeks(day, day)

        assert len(weeks) == 1
        assert date(2026, 1, 26) in weeks  # Week containing Thursday

    def test_full_week_range_monday_to_sunday(self, service):
        """Exactly one week Monday to Sunday."""
        start = date(2026, 1, 26)  # Monday
        end = date(2026, 2, 1)     # Sunday

        weeks = service._get_affected_weeks(start, end)

        assert len(weeks) == 1
        assert date(2026, 1, 26) in weeks

    def test_monday_to_monday_spans_two_weeks(self, service):
        """Monday to next Monday (8 days = 2 weeks)."""
        start = date(2026, 1, 26)  # Monday
        end = date(2026, 2, 2)     # Next Monday

        weeks = service._get_affected_weeks(start, end)

        assert len(weeks) == 2
        assert date(2026, 1, 26) in weeks
        assert date(2026, 2, 2) in weeks

    def test_sunday_to_monday_spans_two_weeks(self, service):
        """Sunday to Monday spans two weeks."""
        start = date(2026, 2, 1)   # Sunday
        end = date(2026, 2, 2)     # Monday

        weeks = service._get_affected_weeks(start, end)

        assert len(weeks) == 2
        assert date(2026, 1, 26) in weeks  # Week containing Sunday
        assert date(2026, 2, 2) in weeks   # Week starting Monday

    def test_friday_to_tuesday_spans_two_weeks(self, service):
        """Friday to next Tuesday spans two weeks."""
        start = date(2026, 1, 30)  # Friday
        end = date(2026, 2, 3)     # Tuesday

        weeks = service._get_affected_weeks(start, end)

        assert len(weeks) == 2

    def test_three_week_span(self, service):
        """Range spanning three weeks."""
        start = date(2026, 1, 28)  # Wednesday
        end = date(2026, 2, 10)    # Tuesday (3 weeks later)

        weeks = service._get_affected_weeks(start, end)

        assert len(weeks) == 3
        assert date(2026, 1, 26) in weeks   # Week 1
        assert date(2026, 2, 2) in weeks    # Week 2
        assert date(2026, 2, 9) in weeks    # Week 3

    @pytest.mark.parametrize("start_day", range(7))
    def test_all_starting_days_two_week_span(self, service, start_day):
        """Test 14-day range starting from each day of week."""
        # Start from a known Monday and offset
        base_monday = date(2026, 1, 26)
        start = base_monday + timedelta(days=start_day)
        end = start + timedelta(days=13)  # 14 days

        weeks = service._get_affected_weeks(start, end)

        # 14 days from any start should hit at least 2 weeks
        assert len(weeks) >= 2

    @pytest.mark.parametrize("start_day", range(7))
    def test_all_starting_days_single_day(self, service, start_day):
        """Test single day for each day of week."""
        base_monday = date(2026, 1, 26)
        day = base_monday + timedelta(days=start_day)

        weeks = service._get_affected_weeks(day, day)

        assert len(weeks) == 1
        # All days in the same week should return the same Monday
        assert date(2026, 1, 26) in weeks

    def test_empty_range_raises_no_error(self, service):
        """When start > end (invalid range), should return empty or handle gracefully."""
        start = date(2026, 2, 4)
        end = date(2026, 1, 29)  # Before start

        weeks = service._get_affected_weeks(start, end)

        # Should return empty set since start > end
        assert len(weeks) == 0

    def test_every_day_covered_by_affected_weeks(self, service):
        """Every day in the range should be covered by one of the affected weeks."""
        start = date(2026, 1, 29)  # Thursday
        end = date(2026, 2, 15)    # Sunday (almost 3 weeks)

        weeks = service._get_affected_weeks(start, end)

        # Verify every day falls within one of the affected weeks
        current = start
        while current <= end:
            week_start = current - timedelta(days=current.weekday())
            assert week_start in weeks, f"Day {current} not covered by any week"
            current += timedelta(days=1)

    def test_leap_year_february(self, service):
        """Test across leap year February boundary."""
        # 2024 is a leap year
        start = date(2024, 2, 26)  # Monday
        end = date(2024, 3, 3)     # Sunday (includes Feb 29)

        weeks = service._get_affected_weeks(start, end)

        assert len(weeks) == 1
        assert date(2024, 2, 26) in weeks

    def test_leap_year_boundary_crossing(self, service):
        """Test crossing into March from leap year February."""
        start = date(2024, 2, 29)  # Thursday (leap day)
        end = date(2024, 3, 5)     # Tuesday

        weeks = service._get_affected_weeks(start, end)

        assert len(weeks) == 2
        assert date(2024, 2, 26) in weeks  # Week containing Feb 29
        assert date(2024, 3, 4) in weeks   # Week starting March 4


class TestGetAffectedWeeksPropertyBased:
    """Property-based tests for _get_affected_weeks using Hypothesis."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return Mock()

    @pytest.fixture
    def service(self, mock_db):
        """Create a WeekOperationService with mocked dependencies."""
        with patch.object(WeekOperationService, '__init__', lambda x, db: None):
            svc = WeekOperationService.__new__(WeekOperationService)
            svc.db = mock_db
            return svc

    @pytest.mark.parametrize("seed", range(20))
    def test_every_day_covered_property(self, service, seed):
        """Property: Every day in range should be covered by an affected week.

        Uses deterministic seeds instead of full hypothesis for faster CI.
        """
        import random
        random.seed(seed)

        # Generate random start date between 2020-2030
        start_ordinal = random.randint(date(2020, 1, 1).toordinal(), date(2030, 12, 31).toordinal())
        start = date.fromordinal(start_ordinal)

        # Generate random range length 0-60 days
        days = random.randint(0, 60)
        end = start + timedelta(days=days)

        weeks = service._get_affected_weeks(start, end)

        # Every day in range should fall within one of the affected weeks
        current = start
        while current <= end:
            week_start = current - timedelta(days=current.weekday())
            assert week_start in weeks, f"Day {current} not covered by any week (seed={seed})"
            current += timedelta(days=1)

    @pytest.mark.parametrize("seed", range(20))
    def test_minimum_weeks_property(self, service, seed):
        """Property: Number of weeks should be at least ceil((days + start_weekday + 1) / 7).

        Uses deterministic seeds instead of full hypothesis for faster CI.
        """
        import random
        random.seed(seed)

        start_ordinal = random.randint(date(2020, 1, 1).toordinal(), date(2030, 12, 31).toordinal())
        start = date.fromordinal(start_ordinal)
        days = random.randint(0, 60)
        end = start + timedelta(days=days)

        weeks = service._get_affected_weeks(start, end)

        # Count actual days in range
        if start <= end:
            # Calculate expected minimum weeks
            # A range spans multiple weeks if it crosses Monday boundaries
            start_monday = start - timedelta(days=start.weekday())
            end_monday = end - timedelta(days=end.weekday())
            expected_min = ((end_monday - start_monday).days // 7) + 1
            assert len(weeks) >= expected_min, f"Expected at least {expected_min} weeks for {start} to {end} (seed={seed})"

    @pytest.mark.parametrize("seed", range(20))
    def test_all_weeks_are_mondays_property(self, service, seed):
        """Property: All returned week starts should be Mondays.

        Uses deterministic seeds instead of full hypothesis for faster CI.
        """
        import random
        random.seed(seed)

        start_ordinal = random.randint(date(2020, 1, 1).toordinal(), date(2030, 12, 31).toordinal())
        start = date.fromordinal(start_ordinal)
        days = random.randint(0, 60)
        end = start + timedelta(days=days)

        weeks = service._get_affected_weeks(start, end)

        for week_start in weeks:
            assert week_start.weekday() == 0, f"{week_start} is not a Monday (seed={seed})"

    @pytest.mark.parametrize("seed", range(20))
    def test_weeks_are_consecutive_property(self, service, seed):
        """Property: Weeks should be consecutive (no gaps).

        Uses deterministic seeds instead of full hypothesis for faster CI.
        """
        import random
        random.seed(seed)

        start_ordinal = random.randint(date(2020, 1, 1).toordinal(), date(2030, 12, 31).toordinal())
        start = date.fromordinal(start_ordinal)
        days = random.randint(0, 60)
        end = start + timedelta(days=days)

        weeks = service._get_affected_weeks(start, end)

        if len(weeks) > 1:
            sorted_weeks = sorted(weeks)
            for i in range(len(sorted_weeks) - 1):
                diff = (sorted_weeks[i + 1] - sorted_weeks[i]).days
                assert diff == 7, f"Gap between weeks: {sorted_weeks[i]} and {sorted_weeks[i + 1]} (seed={seed})"
