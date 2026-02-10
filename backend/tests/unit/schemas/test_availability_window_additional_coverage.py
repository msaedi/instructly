from __future__ import annotations

import datetime as dt

from pydantic import ValidationError
import pytest

from app.schemas.availability_window import (
    ApplyToDateRangeRequest,
    AvailabilityWindowBase,
    AvailabilityWindowUpdate,
    CopyWeekRequest,
    SlotOperation,
    SpecificDateAvailabilityCreate,
    TimeRange,
    WeekSpecificScheduleCreate,
)


def test_availability_window_base_rejects_end_before_start():
    with pytest.raises(ValidationError):
        AvailabilityWindowBase(start_time=dt.time(10, 0), end_time=dt.time(9, 0))


def test_specific_date_availability_rejects_end_before_start():
    with pytest.raises(ValidationError):
        SpecificDateAvailabilityCreate(
            start_time=dt.time(10, 0),
            end_time=dt.time(9, 0),
            specific_date=dt.date(2026, 2, 10),
        )


def test_availability_window_update_validates_optional_and_order():
    payload = AvailabilityWindowUpdate(start_time=dt.time(10, 0), end_time=None)
    assert payload.end_time is None

    with pytest.raises(ValidationError):
        AvailabilityWindowUpdate(start_time=dt.time(10, 0), end_time=dt.time(9, 0))


def test_time_range_rejects_end_before_start():
    with pytest.raises(ValidationError):
        TimeRange(start_time=dt.time(10, 0), end_time=dt.time(9, 0))


def test_week_specific_schedule_requires_monday_week_start():
    with pytest.raises(ValidationError):
        WeekSpecificScheduleCreate(
            schedule=[{"date": "2026-02-10", "start_time": "09:00", "end_time": "10:00"}],
            week_start=dt.date(2026, 2, 10),  # Tuesday
        )


def test_copy_week_request_monday_and_distinct_validations():
    with pytest.raises(ValidationError):
        CopyWeekRequest(
            from_week_start=dt.date(2026, 2, 10),  # Tuesday
            to_week_start=dt.date(2026, 2, 16),
        )

    with pytest.raises(ValidationError):
        CopyWeekRequest(
            from_week_start=dt.date(2026, 2, 9),
            to_week_start=dt.date(2026, 2, 10),  # Tuesday
        )

    with pytest.raises(ValidationError):
        CopyWeekRequest(
            from_week_start=dt.date(2026, 2, 9),
            to_week_start=dt.date(2026, 2, 9),
        )


def test_apply_to_date_range_validations():
    with pytest.raises(ValidationError):
        ApplyToDateRangeRequest(
            from_week_start=dt.date(2026, 2, 10),  # Tuesday
            start_date=dt.date(2026, 2, 10),
            end_date=dt.date(2026, 2, 17),
        )

    with pytest.raises(ValidationError):
        ApplyToDateRangeRequest(
            from_week_start=dt.date(2026, 2, 9),
            start_date=dt.date(2026, 2, 20),
            end_date=dt.date(2026, 2, 19),
        )

    with pytest.raises(ValidationError):
        ApplyToDateRangeRequest(
            from_week_start=dt.date(2026, 2, 9),
            start_date=dt.date(2026, 2, 9),
            end_date=dt.date(2027, 2, 10),
        )


def test_slot_operation_validates_time_order_and_required_date():
    with pytest.raises(ValidationError):
        SlotOperation(action="add", start_time=dt.time(10, 0), end_time=dt.time(9, 0))

    with pytest.raises(ValidationError):
        SlotOperation(action="add", date=None, start_time=dt.time(9, 0), end_time=dt.time(10, 0))
