import datetime as dt

from pydantic import ValidationError
import pytest

from app.schemas.availability_window import (
    ApplyToDateRangeRequest,
    CopyWeekRequest,
    WeekSpecificScheduleCreate,
)


def test_week_specific_schedule_rejects_extra():
    payload = WeekSpecificScheduleCreate(
        schedule=[{"date": "2025-07-15", "start_time": "09:00", "end_time": "10:00"}],
        clear_existing=True,
    )
    with pytest.raises(ValidationError):
        payload.model_validate({
            "schedule": [{"date": "2025-07-15", "start_time": "09:00", "end_time": "10:00"}],
            "clear_existing": True,
            "unexpected": 1,
        })


def test_copy_week_request_rejects_extra():
    base = {
        "from_week_start": dt.date(2025, 7, 14),
        "to_week_start": dt.date(2025, 7, 21),
    }
    # Valid construct works
    _ = CopyWeekRequest(**base)
    # Extra field rejected
    with pytest.raises(ValidationError):
        CopyWeekRequest(**{**base, "unexpected": True})


def test_apply_to_date_range_rejects_extra():
    base = {
        "from_week_start": dt.date(2025, 7, 14),
        "start_date": dt.date(2025, 7, 14),
        "end_date": dt.date(2025, 7, 20),
    }
    _ = ApplyToDateRangeRequest(**base)
    with pytest.raises(ValidationError):
        ApplyToDateRangeRequest(**{**base, "unexpected": "x"})
