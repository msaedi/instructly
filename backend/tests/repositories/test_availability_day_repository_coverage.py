from __future__ import annotations

from datetime import date, timedelta

from app.repositories.availability_day_repository import AvailabilityDayRepository
from app.utils.bitset import new_empty_bits


def _make_bits(*prefix_bytes: int) -> bytes:
    """Build a 36-byte bitmap with the given prefix, zero-padded."""
    b = bytearray(new_empty_bits())
    for i, val in enumerate(prefix_bytes):
        b[i] = val
    return bytes(b)


def test_upsert_week_and_getters(db):
    repo = AvailabilityDayRepository(db)
    instructor_id = "inst-availability"
    week_start = date.today()
    bits = _make_bits(0x00, 0x01, 0x02, 0x03, 0x04, 0x05)

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
    bits = _make_bits(0x01, 0x02, 0x03, 0x04, 0x05, 0x06)

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
    bits = _make_bits(0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C)

    count = repo.bulk_upsert_native(
        [
            (instructor_id, day, bits),
            (instructor_id, day + timedelta(days=1), bits),
        ],
        batch_size=1,
    )
    assert count == 2
    assert repo.get_day_bits(instructor_id, day) == bits


def test_get_day_bits_nonexistent(db):
    """L97: get_day_bits returns None when no matching row."""
    repo = AvailabilityDayRepository(db)
    assert repo.get_day_bits("nonexistent-inst-xyz", date.today()) is None


def test_upsert_week_updates_existing(db):
    """L127: upsert_week updates existing row when one already exists."""
    repo = AvailabilityDayRepository(db)
    instructor_id = "inst-upsert-update"
    day = date.today()
    bits_v1 = _make_bits(0x01, 0x01, 0x01)
    bits_v2 = _make_bits(0x02, 0x02, 0x02)

    repo.upsert_week(instructor_id, [(day, bits_v1)])
    repo.upsert_week(instructor_id, [(day, bits_v2)])

    assert repo.get_day_bits(instructor_id, day) == bits_v2


def test_bulk_upsert_all_empty_list(db):
    """L155: bulk_upsert_all with empty items returns 0."""
    repo = AvailabilityDayRepository(db)
    assert repo.bulk_upsert_all([]) == 0


def test_bulk_upsert_native_empty_list(db):
    """bulk_upsert_native with empty items returns 0."""
    repo = AvailabilityDayRepository(db)
    assert repo.bulk_upsert_native([]) == 0


def test_delete_days_for_instructor_no_exclusions(db):
    """delete_days_for_instructor without exclude_dates deletes all."""
    repo = AvailabilityDayRepository(db)
    instructor_id = "inst-delete-all"
    day = date.today()
    bits = _make_bits(0x01, 0x02, 0x03)

    repo.upsert_week(instructor_id, [(day, bits), (day + timedelta(days=1), bits)])
    deleted = repo.delete_days_for_instructor(instructor_id)
    assert deleted == 2
