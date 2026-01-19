"""Additional unit coverage for AvailabilityService edge branches."""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.availability_service import AvailabilityService
from app.utils.bitset import bits_from_windows, new_empty_bits, windows_from_bits


def test_compute_week_version_bits_empty_map() -> None:
    service = AvailabilityService.__new__(AvailabilityService)

    empty_digest = service.compute_week_version_bits({})
    expected = service.compute_week_version_bits(
        {date(2024, 1, 1): new_empty_bits()}
    )

    assert empty_digest == expected


def test_get_week_bitmap_last_modified_handles_naive_datetime() -> None:
    service = AvailabilityService.__new__(AvailabilityService)

    naive = datetime(2024, 1, 2, 10, 0, 0)
    aware = datetime(2024, 1, 2, 9, 0, 0, tzinfo=timezone.utc)
    rows = [
        SimpleNamespace(updated_at=None),
        SimpleNamespace(updated_at=aware),
        SimpleNamespace(updated_at=naive),
    ]
    repo = SimpleNamespace(get_week_rows=lambda *_: rows)
    service._bitmap_repo = MagicMock(return_value=repo)

    result = service.get_week_bitmap_last_modified("instructor", date(2024, 1, 1))

    assert result is not None
    assert result.tzinfo == timezone.utc
    assert result.hour == 10


def test_resolve_actor_payload_from_roles_list() -> None:
    service = AvailabilityService.__new__(AvailabilityService)

    class Role:
        def __init__(self, name: str) -> None:
            self.name = name

    class Actor:
        def __init__(self) -> None:
            self.id = "actor-1"
            self.roles = [Role("admin")]

    payload = service._resolve_actor_payload(Actor())

    assert payload == {"id": "actor-1", "role": "admin"}


def test_build_week_audit_payload_uses_cache_and_delta() -> None:
    service = AvailabilityService.__new__(AvailabilityService)
    service.compute_week_version = MagicMock(return_value="v1")

    date_one = date(2024, 1, 1)
    date_two = date(2024, 1, 2)
    window_cache = {date_one: [("09:00:00", "10:00:00")]}

    bits = bits_from_windows([("10:00:00", "11:00:00")])
    repo = SimpleNamespace(get_day_bits=lambda *_: bits)
    service._bitmap_repo = MagicMock(return_value=repo)

    payload = service._build_week_audit_payload(
        instructor_id="instructor",
        week_start=date_one,
        dates=[date_one, date_two],
        clear_existing=False,
        created=2,
        window_cache=window_cache,
    )

    assert payload["window_counts"][date_one.isoformat()] == 1
    assert payload["window_counts"][date_two.isoformat()] == 1
    assert payload["delta"] == {"created": 2, "deleted": 0}
    assert window_cache[date_two] == windows_from_bits(bits)


def test_get_availability_summary_counts_windows() -> None:
    service = AvailabilityService.__new__(AvailabilityService)
    date_one = date(2024, 1, 1)
    date_two = date(2024, 1, 2)
    rows = [
        SimpleNamespace(day_date=date_one, bits=bits_from_windows([("09:00:00", "10:00:00")])),
        SimpleNamespace(day_date=date_two, bits=new_empty_bits()),
    ]
    repo = SimpleNamespace(get_days_in_range=lambda *_: rows)
    service._bitmap_repo = MagicMock(return_value=repo)

    result = service.get_availability_summary("instructor", date_one, date_two)

    assert result == {date_one.isoformat(): 1}


def test_get_availability_summary_returns_empty_on_error() -> None:
    service = AvailabilityService.__new__(AvailabilityService)
    service._bitmap_repo = MagicMock(side_effect=RuntimeError("boom"))

    result = service.get_availability_summary("instructor", date(2024, 1, 1), date(2024, 1, 2))

    assert result == {}
