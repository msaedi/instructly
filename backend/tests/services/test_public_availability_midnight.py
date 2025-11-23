from datetime import date, datetime, time

import pytz

from app.repositories.availability_day_repository import AvailabilityDayRepository
from app.services.availability_service import AvailabilityService
from app.utils.bitset import bits_from_windows


def test_compute_public_availability_keeps_midnight_windows(db, test_instructor, monkeypatch):
    """Ensure late-night windows ending at midnight survive min-advance trimming."""

    profile = test_instructor.instructor_profile
    profile.min_advance_booking_hours = 3
    profile.buffer_time_minutes = 0
    db.flush()

    target_date = date.today()
    repo = AvailabilityDayRepository(db)
    repo.delete_days_for_instructor(test_instructor.id)
    repo.upsert_week(
        test_instructor.id,
        [(target_date, bits_from_windows([("21:00:00", "24:00:00")]))],
    )

    tz_name = getattr(test_instructor, "timezone", None) or "America/New_York"
    tz = pytz.timezone(tz_name)
    fake_now = tz.localize(datetime.combine(target_date, time(20, 0)))

    def _fake_now(_user_id, _db_session):
        return fake_now

    monkeypatch.setattr("app.services.availability_service.get_user_now_by_id", _fake_now)

    service = AvailabilityService(db)
    result = service.compute_public_availability(test_instructor.id, target_date, target_date)
    slots = result[target_date.isoformat()]

    assert slots, "Late-night availability ending at midnight should remain after trimming"
    assert slots[0][0] >= time(23, 0)
    assert slots[0][1] == time(0, 0)
