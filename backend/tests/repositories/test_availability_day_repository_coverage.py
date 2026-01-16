from __future__ import annotations

from datetime import date, timedelta

from app.repositories.availability_day_repository import AvailabilityDayRepository


def test_upsert_week_and_getters(db):
    repo = AvailabilityDayRepository(db)
    instructor_id = "inst-availability"
    week_start = date.today()
    bits = b"\x00\x01\x02\x03\x04\x05"

    count = repo.upsert_week(
        instructor_id,
        [(week_start, bits), (week_start + timedelta(days=1), bits)],
    )
    assert count == 2

    assert repo.get_day_bits(instructor_id, week_start) == bits
    week = repo.get_week(instructor_id, week_start)
    assert week[week_start] == bits

    rows = repo.get_days_in_range(
        instructor_id, week_start, week_start + timedelta(days=1)
    )
    assert len(rows) == 2


def test_bulk_upsert_all_and_delete(db):
    repo = AvailabilityDayRepository(db)
    instructor_id = "inst-bulk"
    day = date.today()
    bits = b"\x01\x02\x03\x04\x05\x06"

    count = repo.bulk_upsert_all(
        [
            (instructor_id, day, bits),
            (instructor_id, day + timedelta(days=1), bits),
        ]
    )
    assert count == 2

    deleted = repo.delete_days_for_instructor(
        instructor_id, exclude_dates=[day]
    )
    assert deleted == 1


def test_bulk_upsert_native(db):
    repo = AvailabilityDayRepository(db)
    instructor_id = "inst-native"
    day = date.today()
    bits = b"\x07\x08\x09\x0a\x0b\x0c"

    count = repo.bulk_upsert_native(
        [
            (instructor_id, day, bits),
            (instructor_id, day + timedelta(days=1), bits),
        ],
        batch_size=1,
    )
    assert count == 2
    assert repo.get_day_bits(instructor_id, day) == bits
