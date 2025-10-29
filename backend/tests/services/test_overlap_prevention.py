from __future__ import annotations

from datetime import time, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from tests.utils.availability_builders import future_week_start, slot_entry

from app.core.exceptions import AvailabilityOverlapException
from app.models.availability import AvailabilitySlot
from app.schemas.availability_window import WeekSpecificScheduleCreate
from app.services.availability_service import AvailabilityService


@pytest.mark.asyncio
async def test_rejects_true_overlap_same_day(db, test_instructor) -> None:
    service = AvailabilityService(db)
    monday = future_week_start(weeks_ahead=3)

    payload = WeekSpecificScheduleCreate(
        week_start=monday,
        clear_existing=True,
        schedule=[
            slot_entry(monday, "10:00", "11:00"),
            slot_entry(monday, "10:30", "11:30"),
        ],
    )

    with pytest.raises(AvailabilityOverlapException):
        await service.save_week_availability(test_instructor.id, payload)

    remaining = (
        db.query(AvailabilitySlot)
        .filter(AvailabilitySlot.instructor_id == test_instructor.id)
        .count()
    )
    assert remaining == 0


@pytest.mark.asyncio
async def test_allows_touching_edges(db, test_instructor) -> None:
    service = AvailabilityService(db)
    monday = future_week_start(weeks_ahead=4)

    payload = WeekSpecificScheduleCreate(
        week_start=monday,
        clear_existing=True,
        schedule=[
            slot_entry(monday, "10:00", "11:00"),
            slot_entry(monday, "11:00", "12:00"),
        ],
    )

    await service.save_week_availability(test_instructor.id, payload)
    week_map = service.get_week_availability(test_instructor.id, monday)
    assert len(week_map[monday.isoformat()]) == 2


@pytest.mark.asyncio
async def test_overnight_payload_persists_split_segments(db, test_instructor) -> None:
    service = AvailabilityService(db)
    monday = future_week_start(weeks_ahead=4)

    payload = WeekSpecificScheduleCreate(
        week_start=monday,
        clear_existing=True,
        schedule=[slot_entry(monday, "23:30", "01:00")],
    )

    await service.save_week_availability(test_instructor.id, payload)
    slots = (
        db.query(AvailabilitySlot)
        .filter(AvailabilitySlot.instructor_id == test_instructor.id)
        .order_by(AvailabilitySlot.specific_date, AvailabilitySlot.start_time)
        .all()
    )

    assert len(slots) == 2
    assert slots[0].specific_date == monday
    assert slots[0].start_time.strftime("%H:%M") == "23:30"
    assert slots[0].end_time.strftime("%H:%M") == "00:00"

    next_day = monday + timedelta(days=1)
    assert slots[1].specific_date == next_day
    assert slots[1].start_time.strftime("%H:%M") == "00:00"
    assert slots[1].end_time.strftime("%H:%M") == "01:00"


@pytest.mark.asyncio
async def test_detects_overlap_against_existing(db, test_instructor) -> None:
    service = AvailabilityService(db)
    monday = future_week_start(weeks_ahead=5)

    existing_payload = WeekSpecificScheduleCreate(
        week_start=monday,
        clear_existing=True,
        schedule=[slot_entry(monday, "09:00", "10:00")],
    )
    await service.save_week_availability(test_instructor.id, existing_payload)

    overlapping_payload = WeekSpecificScheduleCreate(
        week_start=monday,
        clear_existing=False,
        schedule=[slot_entry(monday, "09:30", "09:45")],
    )

    with pytest.raises(AvailabilityOverlapException):
        await service.save_week_availability(test_instructor.id, overlapping_payload)

    slots = (
        db.query(AvailabilitySlot)
        .filter(AvailabilitySlot.instructor_id == test_instructor.id)
        .all()
    )
    assert [(s.start_time.strftime("%H:%M"), s.end_time.strftime("%H:%M")) for s in slots] == [
        ("09:00", "10:00")
    ]


@pytest.mark.asyncio
async def test_existing_slots_fetched_once_per_date(
    db, test_instructor, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = AvailabilityService(db)
    monday = future_week_start(weeks_ahead=6)

    initial_payload = WeekSpecificScheduleCreate(
        week_start=monday,
        clear_existing=True,
        schedule=[slot_entry(monday, "08:00", "09:00")],
    )
    await service.save_week_availability(test_instructor.id, initial_payload)

    call_counter = {"count": 0}
    original_get = service.repository.get_slots_by_date

    def wrapped_get(*args, **kwargs):
        call_counter["count"] += 1
        return original_get(*args, **kwargs)

    monkeypatch.setattr(service.repository, "get_slots_by_date", wrapped_get)

    follow_up = WeekSpecificScheduleCreate(
        week_start=monday,
        clear_existing=False,
        schedule=[
            slot_entry(monday, "09:00", "10:00"),
            slot_entry(monday, "10:00", "11:00"),
            slot_entry(monday, "11:00", "12:00"),
        ],
    )

    await service.save_week_availability(test_instructor.id, follow_up)
    assert call_counter["count"] == 1


def test_db_constraint_blocks_overlap(db, test_instructor) -> None:
    monday = future_week_start(weeks_ahead=7)
    slot_a = AvailabilitySlot(
        instructor_id=test_instructor.id,
        specific_date=monday,
        start_time=time.fromisoformat("13:00"),
        end_time=time.fromisoformat("14:00"),
    )
    db.add(slot_a)
    db.commit()

    overlapping = AvailabilitySlot(
        instructor_id=test_instructor.id,
        specific_date=monday,
        start_time=time.fromisoformat("13:30"),
        end_time=time.fromisoformat("14:30"),
    )
    db.add(overlapping)

    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
