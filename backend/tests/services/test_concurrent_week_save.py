from __future__ import annotations

from datetime import timedelta

import pytest
from tests.utils.availability_builders import future_week_start, slot_entry

from app.core.exceptions import ConflictException
from app.schemas.availability_window import WeekSpecificScheduleCreate
from app.services.availability_service import AvailabilityService


@pytest.mark.asyncio
async def test_save_week_conflict_on_stale_version(db, test_instructor) -> None:
    """
    Simulate concurrent edits: a stale version should raise ConflictException.
    """

    service = AvailabilityService(db)
    monday = future_week_start(weeks_ahead=4)

    initial_payload = WeekSpecificScheduleCreate(
        week_start=monday,
        clear_existing=True,
        schedule=[slot_entry(monday, "09:00", "10:00")],
    )
    await service.save_week_availability(test_instructor.id, initial_payload)

    current_version = service.compute_week_version(
        test_instructor.id, monday, monday + timedelta(days=6)
    )

    stale_payload = WeekSpecificScheduleCreate(
        week_start=monday,
        clear_existing=True,
        version="stale-version",
        schedule=[slot_entry(monday, "11:00", "12:00")],
    )

    with pytest.raises(ConflictException):
        await service.save_week_availability(test_instructor.id, stale_payload)

    fresh_payload = WeekSpecificScheduleCreate(
        week_start=monday,
        clear_existing=True,
        version=current_version,
        schedule=[slot_entry(monday, "11:00", "12:00")],
    )
    await service.save_week_availability(test_instructor.id, fresh_payload)

    week_map = service.get_week_availability(test_instructor.id, monday)
    slots = week_map[monday.isoformat()]
    assert slots == [{"start_time": "11:00:00", "end_time": "12:00:00"}]
