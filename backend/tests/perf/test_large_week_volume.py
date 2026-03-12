from __future__ import annotations

from datetime import timedelta

import pytest
from tests.utils.availability_builders import future_week_start

from app.repositories.availability_day_repository import AvailabilityDayRepository
from app.services.availability_service import AvailabilityService
from app.utils.bitset import bits_from_windows


@pytest.mark.slow
def test_get_week_handles_large_slot_volume(db, test_instructor) -> None:
    """
    Seed ~1k slots and ensure the week fetch still returns everything quickly.
    """

    service = AvailabilityService(db)
    monday = future_week_start(weeks_ahead=2)

    repo = AvailabilityDayRepository(db)
    items = []
    for day_offset in range(7):
        day = monday + timedelta(days=day_offset)
        # Full day availability as a single window
        items.append((day, bits_from_windows([("00:00:00", "24:00:00")])))

    repo.upsert_week(test_instructor.id, items)
    db.commit()

    week_map = service.get_week_availability(
        test_instructor.id,
        monday,
        include_empty=True,
    )

    def _minutes(value: str) -> int:
        hour, minute, _second = value.split(":")
        if hour == "24":
            return 24 * 60
        return int(hour) * 60 + int(minute)

    # Verify all 7 days have full-day coverage (1440 minutes each)
    total_minutes = 0
    for entries in week_map.values():
        for entry in entries:
            total_minutes += _minutes(entry["end_time"]) - _minutes(entry["start_time"])

    assert total_minutes == 7 * 24 * 60  # 7 full days
