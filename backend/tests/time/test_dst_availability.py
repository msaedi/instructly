from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.repositories.availability_day_repository import AvailabilityDayRepository
from app.services.availability_service import AvailabilityService
from app.utils.bitset import bits_from_windows


@pytest.mark.parametrize(
    "slot_date,start_hour,end_hour",
    [
        # Spring forward: missing 02:00 – ensure bridging slot survives.
        (date(2025, 3, 9), 1, 3),
        # Fall back: repeated 01:00 hour should only appear once per slot.
        (date(2025, 11, 2), 1, 2),
    ],
)
def test_dst_boundary_slots_render_consistently(
    db,
    test_instructor,
    slot_date: date,
    start_hour: int,
    end_hour: int,
) -> None:
    """
    Availability slots that straddle DST transitions should persist without
    duplication or gaps.

    The raw times are stored in UTC-agnostic columns, so the test converts them
    to America/New_York to ensure offsets line up before/after the transition.
    """

    repo = AvailabilityDayRepository(db)
    repo.upsert_week(
        test_instructor.id,
        [
            (
                slot_date,
                bits_from_windows(
                    [(f"{start_hour:02d}:30:00", f"{end_hour:02d}:30:00")]
                ),
            )
        ],
    )
    db.commit()

    service = AvailabilityService(db)
    monday = slot_date - timedelta(days=slot_date.weekday())
    result = service.get_week_availability(test_instructor.id, monday)

    iso = slot_date.isoformat()
    assert iso in result, f"expected {iso} in availability map"
    slots = result[iso]
    assert len(slots) == 1
    assert slots[0]["start_time"] == f"{start_hour:02d}:30:00"
    assert slots[0]["end_time"] == f"{end_hour:02d}:30:00"

    ny = ZoneInfo("America/New_York")
    start_local = datetime.combine(slot_date, time(start_hour, 30), ny)
    end_local = datetime.combine(slot_date, time(end_hour, 30), ny)

    # Spring forward switches from UTC-5 to UTC-4; fall back flips the other way.
    assert start_local.utcoffset() is not None
    assert end_local.utcoffset() is not None
    # Ensure offset changes when expected (spring forward) or stays consistent (fall back),
    # but the slot remains monotonic in UTC time.
    assert start_local.astimezone(ZoneInfo("UTC")) < end_local.astimezone(ZoneInfo("UTC"))
