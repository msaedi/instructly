from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import RepositoryException
from app.repositories.week_operation_repository import WeekOperationRepository


def test_get_week_bookings_with_slots_summary(db, test_booking):
    repo = WeekOperationRepository(db)
    week_dates = [test_booking.booking_date]

    summary = repo.get_week_bookings_with_slots(test_booking.instructor_id, week_dates)

    assert summary["total_bookings"] >= 1
    assert test_booking.booking_date.isoformat() in summary["booked_time_ranges_by_date"]


def test_get_bookings_in_date_range_summary(db, test_booking):
    repo = WeekOperationRepository(db)
    start_date = test_booking.booking_date - timedelta(days=1)
    end_date = test_booking.booking_date + timedelta(days=1)

    summary = repo.get_bookings_in_date_range(test_booking.instructor_id, start_date, end_date)

    assert summary["total_bookings"] >= 1
    assert test_booking.booking_date.isoformat() in summary["bookings_by_date"]


@pytest.mark.parametrize(
    "method_name,args",
    [
        ("get_week_slots", ("inst1", date.today(), date.today())),
        ("get_slots_with_booking_status", ("inst1", date.today())),
        ("get_week_with_booking_status", ("inst1", date.today(), date.today())),
        ("bulk_create_slots", ([],)),
        ("bulk_delete_slots", ([1, 2],)),
        ("delete_slots_preserving_booked_times", ("inst1", [date.today()], True)),
    ],
)
def test_slot_methods_raise_not_implemented(method_name, args):
    repo = WeekOperationRepository(MagicMock())
    with pytest.raises(NotImplementedError):
        getattr(repo, method_name)(*args)


@pytest.mark.parametrize(
    "method_name,args",
    [
        ("get_week_bookings_with_slots", ("inst1", [date.today()])),
        ("get_bookings_in_date_range", ("inst1", date.today(), date.today())),
    ],
)
def test_repo_errors_raise_repository_exception(method_name, args):
    db = MagicMock()
    db.query.side_effect = SQLAlchemyError("boom")
    repo = WeekOperationRepository(db)

    with pytest.raises(RepositoryException):
        getattr(repo, method_name)(*args)
