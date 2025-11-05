from __future__ import annotations

from datetime import date, timedelta

import pytest
from tests.utils.availability_builders import future_week_start, slot_entry

from app.repositories.availability_day_repository import AvailabilityDayRepository
from app.schemas.availability_window import WeekSpecificScheduleCreate
from app.services.availability_service import AvailabilityService
from app.utils.bitset import bits_from_windows


def test_slot_ending_at_midnight_round_trips(db, test_instructor) -> None:
    """A slot finishing at 00:00 renders without losing the midnight boundary."""
    monday = future_week_start()
    slot_day = monday
    repo = AvailabilityDayRepository(db)
    repo.upsert_week(
        test_instructor.id,
        [(slot_day, bits_from_windows([("22:30:00", "24:00:00")]))],
    )
    db.commit()

    service = AvailabilityService(db)
    result = service.get_week_availability(test_instructor.id, monday)

    day_entries = result[slot_day.isoformat()]
    assert len(day_entries) == 1
    entry = day_entries[0]
    assert entry["start_time"] == "22:30:00"
    assert entry["end_time"] in {"00:00:00", "24:00:00"}

    next_day = slot_day + timedelta(days=1)
    assert next_day.isoformat() not in result


@pytest.mark.asyncio
async def test_overnight_slot_splits_across_midnight(db, test_instructor) -> None:
    """Overnight inputs split into two segments across the boundary."""
    service = AvailabilityService(db)
    monday = future_week_start()
    payload = WeekSpecificScheduleCreate(
        week_start=monday,
        clear_existing=True,
        schedule=[
            slot_entry(monday, "22:00", "01:00"),  # crosses midnight
        ],
    )

    await service.save_week_availability(test_instructor.id, payload)
    result = service.get_week_availability(test_instructor.id, monday)
    day_entry = result[monday.isoformat()]
    assert len(day_entry) == 1
    assert day_entry[0]["start_time"] == "22:00:00"
    assert day_entry[0]["end_time"] in {"00:00:00", "24:00:00"}

    tuesday = monday + timedelta(days=1)
    spill_entry = result[tuesday.isoformat()]
    assert len(spill_entry) == 1
    assert spill_entry[0]["start_time"] == "00:00:00"
    assert spill_entry[0]["end_time"] == "01:00:00"


def test_week_rollover_aligns_with_requested_monday(db, test_instructor) -> None:
    """Week map keys should stay within the requested Monday..Sunday window."""
    monday = date(2025, 12, 1)  # explicit future Monday for determinism in tests
    sunday = monday + timedelta(days=6)
    repo = AvailabilityDayRepository(db)
    repo.upsert_week(
        test_instructor.id,
        [
            (monday, bits_from_windows([("09:00:00", "10:00:00")])),
            (sunday, bits_from_windows([("11:00:00", "12:00:00")])),
        ],
    )
    db.commit()

    service = AvailabilityService(db)
    result = service.get_week_availability(test_instructor.id, monday)

    assert list(sorted(result.keys())) == [monday.isoformat(), sunday.isoformat()]
