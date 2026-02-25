"""Unit coverage for AnalyticsRepository – uncovered L64,66,82,84."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.repositories.analytics_repository import AnalyticsRepository


def _make_repo() -> tuple[AnalyticsRepository, MagicMock]:
    mock_db = MagicMock()
    repo = AnalyticsRepository(mock_db)
    return repo, mock_db


class TestListBookingsByStart:
    """L64,66: optional statuses and instructor_ids filters."""

    def test_with_statuses_filter(self) -> None:
        repo, mock_db = _make_repo()
        query = MagicMock()
        mock_db.query.return_value = query
        query.options.return_value = query
        query.filter.return_value = query
        query.all.return_value = []

        now = datetime.now(timezone.utc)
        result = repo.list_bookings_by_start(
            start=now, end=now, statuses=["CONFIRMED"]
        )
        assert result == []

    def test_with_instructor_ids_filter(self) -> None:
        repo, mock_db = _make_repo()
        query = MagicMock()
        mock_db.query.return_value = query
        query.options.return_value = query
        query.filter.return_value = query
        query.all.return_value = []

        now = datetime.now(timezone.utc)
        result = repo.list_bookings_by_start(
            start=now, end=now, instructor_ids=["inst-01"]
        )
        assert result == []

    def test_without_filters(self) -> None:
        repo, mock_db = _make_repo()
        query = MagicMock()
        mock_db.query.return_value = query
        query.options.return_value = query
        query.filter.return_value = query
        query.all.return_value = []

        now = datetime.now(timezone.utc)
        result = repo.list_bookings_by_start(start=now, end=now)
        assert result == []


class TestListBookingsByCreated:
    """L82,84: optional statuses and instructor_ids filters."""

    def test_with_statuses_filter(self) -> None:
        repo, mock_db = _make_repo()
        query = MagicMock()
        mock_db.query.return_value = query
        query.filter.return_value = query
        query.all.return_value = []

        now = datetime.now(timezone.utc)
        result = repo.list_bookings_by_created(
            start=now, end=now, statuses=["COMPLETED"]
        )
        assert result == []

    def test_with_instructor_ids_filter(self) -> None:
        repo, mock_db = _make_repo()
        query = MagicMock()
        mock_db.query.return_value = query
        query.filter.return_value = query
        query.all.return_value = []

        now = datetime.now(timezone.utc)
        result = repo.list_bookings_by_created(
            start=now, end=now, instructor_ids=["inst-01"]
        )
        assert result == []


class TestCountBookings:
    """date_field branching."""

    def test_date_field_created_at(self) -> None:
        repo, mock_db = _make_repo()
        query = MagicMock()
        mock_db.query.return_value = query
        query.filter.return_value = query
        query.join.return_value = query
        query.scalar.return_value = 10

        now = datetime.now(timezone.utc)
        result = repo.count_bookings(
            start=now, end=now, date_field="created_at"
        )
        assert result == 10

    def test_date_field_booking_start(self) -> None:
        repo, mock_db = _make_repo()
        query = MagicMock()
        mock_db.query.return_value = query
        query.filter.return_value = query
        query.scalar.return_value = 0

        now = datetime.now(timezone.utc)
        result = repo.count_bookings(
            start=now, end=now, date_field="booking_start_utc"
        )
        assert result == 0

    def test_with_service_catalog_ids(self) -> None:
        repo, mock_db = _make_repo()
        query = MagicMock()
        mock_db.query.return_value = query
        query.filter.return_value = query
        query.join.return_value = query
        query.scalar.return_value = 2

        now = datetime.now(timezone.utc)
        result = repo.count_bookings(
            start=now,
            end=now,
            date_field="created_at",
            service_catalog_ids=["cat-01"],
        )
        assert result == 2


class TestListAvailabilityDays:
    """Empty instructor_ids early return."""

    def test_empty_ids_returns_empty(self) -> None:
        repo, _ = _make_repo()
        from datetime import date

        result = repo.list_availability_days(
            instructor_ids=[], start_date=date.today(), end_date=date.today()
        )
        assert result == []


class TestListUserIdsWithBookings:
    """Empty user_ids early return."""

    def test_empty_ids_returns_empty_set(self) -> None:
        repo, _ = _make_repo()
        now = datetime.now(timezone.utc)
        result = repo.list_user_ids_with_bookings(
            user_ids=[], role="student", start=now, end=now
        )
        assert result == set()
