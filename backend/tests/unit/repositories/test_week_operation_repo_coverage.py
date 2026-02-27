"""Unit coverage for WeekOperationRepository – uncovered lines L131,136,194,198.

L131: booking_date is None → continue
L136: start_time/end_time are not time instances → continue
L194: booking_date is None → continue in date-range method
L198: start_time/end_time are not time instances → continue in date-range method
"""

from __future__ import annotations

from datetime import date, time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import RepositoryException
from app.repositories.week_operation_repository import WeekOperationRepository


def _make_row(booking_date=None, start_time=None, end_time=None):
    """Create a mock row with _mapping attribute."""
    mapping = {
        "booking_date": booking_date,
        "start_time": start_time,
        "end_time": end_time,
    }
    row = SimpleNamespace(_mapping=mapping)
    return row


def _setup_query_mock(mock_db, rows):
    """Set up a MagicMock db.query chain that returns rows from .all()."""
    # MagicMock auto-chains .filter() etc. but we need .all() at any depth
    chain = MagicMock()
    chain.all.return_value = rows
    chain.filter.return_value = chain
    mock_db.query.return_value = chain


@pytest.mark.unit
class TestGetWeekBookingsNoneDateAndNonTimeValues:
    """Cover L131 (booking_date None) and L136 (non-time values) in get_week_bookings_with_slots."""

    def test_booking_date_none_skipped(self) -> None:
        """L130-131: booking_date is None → row skipped via continue."""
        mock_db = MagicMock()
        repo = WeekOperationRepository(mock_db)

        row_with_none_date = _make_row(
            booking_date=None,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )
        row_valid = _make_row(
            booking_date=date(2025, 3, 1),
            start_time=time(14, 0),
            end_time=time(15, 0),
        )

        _setup_query_mock(mock_db, [row_with_none_date, row_valid])

        result = repo.get_week_bookings_with_slots(
            instructor_id="INST_01",
            week_dates=[date(2025, 3, 1)],
        )

        assert result["total_bookings"] == 2  # both rows counted
        # But only the valid one produces a time range entry
        assert len(result["booked_time_ranges_by_date"]) == 1
        assert "2025-03-01" in result["booked_time_ranges_by_date"]

    def test_non_time_values_skipped(self) -> None:
        """L135-136: start_time/end_time that are not time instances → continue."""
        mock_db = MagicMock()
        repo = WeekOperationRepository(mock_db)

        row_bad_times = _make_row(
            booking_date=date(2025, 3, 1),
            start_time="09:00",  # string, not time
            end_time="10:00",
        )
        row_valid = _make_row(
            booking_date=date(2025, 3, 1),
            start_time=time(14, 0),
            end_time=time(15, 0),
        )

        _setup_query_mock(mock_db, [row_bad_times, row_valid])

        result = repo.get_week_bookings_with_slots(
            instructor_id="INST_01",
            week_dates=[date(2025, 3, 1)],
        )

        # Only one valid time range despite two rows
        ranges = result["booked_time_ranges_by_date"].get("2025-03-01", [])
        assert len(ranges) == 1
        assert ranges[0]["start_time"] == time(14, 0)


@pytest.mark.unit
class TestGetBookingsInDateRangeNoneDateAndNonTimeValues:
    """Cover L194 (booking_date None) and L198 (non-time values) in get_bookings_in_date_range."""

    def test_booking_date_none_skipped(self) -> None:
        """L192-194: booking_date is None → row skipped via continue."""
        mock_db = MagicMock()
        repo = WeekOperationRepository(mock_db)

        row_with_none_date = _make_row(
            booking_date=None,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )
        row_valid = _make_row(
            booking_date=date(2025, 3, 2),
            start_time=time(11, 0),
            end_time=time(12, 0),
        )

        _setup_query_mock(mock_db, [row_with_none_date, row_valid])

        result = repo.get_bookings_in_date_range(
            instructor_id="INST_01",
            start_date=date(2025, 3, 1),
            end_date=date(2025, 3, 7),
        )

        assert result["total_bookings"] == 2
        assert len(result["bookings_by_date"]) == 1
        assert "2025-03-02" in result["bookings_by_date"]

    def test_non_time_values_skipped(self) -> None:
        """L196-198: start_time/end_time not time instances → continue."""
        mock_db = MagicMock()
        repo = WeekOperationRepository(mock_db)

        row_bad_times = _make_row(
            booking_date=date(2025, 3, 2),
            start_time=None,
            end_time=None,
        )
        row_valid = _make_row(
            booking_date=date(2025, 3, 2),
            start_time=time(16, 0),
            end_time=time(17, 0),
        )

        _setup_query_mock(mock_db, [row_bad_times, row_valid])

        result = repo.get_bookings_in_date_range(
            instructor_id="INST_01",
            start_date=date(2025, 3, 1),
            end_date=date(2025, 3, 7),
        )

        ranges = result["bookings_by_date"].get("2025-03-02", [])
        assert len(ranges) == 1
        assert ranges[0]["start_time"] == time(16, 0)



@pytest.mark.unit
class TestSQLAlchemyErrors:
    """Cover SQLAlchemyError exception paths."""

    def test_get_week_bookings_sqlalchemy_error(self) -> None:
        mock_db = MagicMock()
        repo = WeekOperationRepository(mock_db)
        mock_db.query.side_effect = SQLAlchemyError("db error")

        with pytest.raises(RepositoryException, match="Failed to get week bookings"):
            repo.get_week_bookings_with_slots("INST_01", [date(2025, 3, 1)])

    def test_get_bookings_in_date_range_sqlalchemy_error(self) -> None:
        mock_db = MagicMock()
        repo = WeekOperationRepository(mock_db)
        mock_db.query.side_effect = SQLAlchemyError("db error")

        with pytest.raises(RepositoryException, match="Failed to get bookings"):
            repo.get_bookings_in_date_range("INST_01", date(2025, 3, 1), date(2025, 3, 7))
