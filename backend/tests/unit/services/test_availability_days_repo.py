from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.repositories.availability_day_repository import AvailabilityDayRepository
from app.utils.bitset import (
    bits_from_windows,
    new_empty_bits,
    toggle_index,
    unpack_indexes,
    windows_from_bits,
)


def test_bit_helpers_roundtrip():
    bits = new_empty_bits()
    bits = toggle_index(bits, 18, True)  # 09:00-09:30
    bits = toggle_index(bits, 19, True)  # 09:30-10:00
    idxs = unpack_indexes(bits)
    assert 18 in idxs and 19 in idxs
    wins = windows_from_bits(bits)
    assert wins == [("09:00:00", "10:00:00")]
    back = bits_from_windows(wins)
    assert back == bits


def test_repo_upsert_and_get_week(unit_db: Session):
    repo = AvailabilityDayRepository(unit_db)
    monday = date(2025, 11, 3)
    payload = []
    # Set 09:00-10:00 on Mon-Wed
    for offset in range(3):
        day = monday + timedelta(days=offset)
        bits = bits_from_windows([("09:00:00", "10:00:00")])
        payload.append((day, bits))
    written = repo.upsert_week("instructor-1", payload)
    assert written == 3

    week = repo.get_week("instructor-1", monday)
    assert len(week) == 3
    mon_bits = week[monday]
    assert windows_from_bits(mon_bits) == [("09:00:00", "10:00:00")]
