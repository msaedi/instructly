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
    total_slots = 0
    items = []
    for day_offset in range(7):
        day = monday + timedelta(days=day_offset)
        windows = []
        for segment in range(48):  # 30-minute segments across the day
            start_minutes = segment * 30
            end_minutes = start_minutes + 30
            start_hour, start_minute = divmod(start_minutes, 60)
            end_hour, end_minute = divmod(end_minutes, 60)
            start_str = f"{start_hour:02d}:{start_minute:02d}:00"
            end_str = f"{end_hour:02d}:{end_minute:02d}:00" if end_hour < 24 else "24:00:00"
            windows.append((start_str, end_str))
        total_slots += len(windows)
        items.append((day, bits_from_windows(windows)))

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

    returned = 0
    for entries in week_map.values():
        for entry in entries:
            returned += (_minutes(entry["end_time"]) - _minutes(entry["start_time"])) // 30

    assert returned == total_slots
