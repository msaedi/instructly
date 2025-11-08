from __future__ import annotations

from datetime import date, time
from types import SimpleNamespace
from unittest.mock import Mock

from app.services.week_operation_service import WeekOperationService


class _StubAvailabilityService:
    def get_week_availability(self, instructor_id: str, from_week_start: date) -> dict:  # pragma: no cover - helper
        return {}


class _StubAvailabilityRepository:
    def delete_slots_by_dates(self, instructor_id: str, week_dates):  # pragma: no cover - helper
        return 0


def _build_service(slot_start: time, slot_end: time) -> tuple[WeekOperationService, Mock]:
    repo = Mock()
    repo.get_week_slots.return_value = [
        SimpleNamespace(specific_date=date(2025, 1, 6), start_time=slot_start, end_time=slot_end)
    ]
    repo.bulk_create_slots.return_value = 1

    service = WeekOperationService.__new__(WeekOperationService)
    service.db = None  # not used
    service.repository = repo
    service.availability_repository = _StubAvailabilityRepository()
    service.availability_service = _StubAvailabilityService()
    service.conflict_checker = None
    service.cache_service = None
    service.logger = Mock()
    return service, repo


def test_copy_week_skips_contained_slots() -> None:
    service, repo = _build_service(slot_start=time(10, 0), slot_end=time(12, 0))

    existing_slot = SimpleNamespace(
        instructor_id="instr",
        specific_date=date(2025, 1, 13),
        start_time=time(9, 0),
        end_time=time(13, 0),
    )

    created = service._copy_slots_between_weeks(
        instructor_id="instr",
        from_week_start=date(2025, 1, 6),
        to_week_start=date(2025, 1, 13),
        existing_target_slots=[existing_slot],
    )

    assert created == 1
    repo.bulk_create_slots.assert_called_once()
    payload = repo.bulk_create_slots.call_args.args[0]
    assert payload == [
        {
            "instructor_id": "instr",
            "specific_date": date(2025, 1, 13),
            "start_time": time(9, 0),
            "end_time": time(13, 0),
        }
    ]


def test_copy_week_replaces_subsumed_slots() -> None:
    service, repo = _build_service(slot_start=time(9, 0), slot_end=time(13, 0))

    existing_slots = [
        SimpleNamespace(
            instructor_id="instr",
            specific_date=date(2025, 1, 13),
            start_time=time(9, 0),
            end_time=time(11, 0),
        ),
        SimpleNamespace(
            instructor_id="instr",
            specific_date=date(2025, 1, 13),
            start_time=time(11, 0),
            end_time=time(13, 0),
        ),
    ]

    created = service._copy_slots_between_weeks(
        instructor_id="instr",
        from_week_start=date(2025, 1, 6),
        to_week_start=date(2025, 1, 13),
        existing_target_slots=existing_slots,
    )

    assert created == 1
    repo.bulk_create_slots.assert_called_once()
    payload = repo.bulk_create_slots.call_args.args[0]
    assert payload == [
        {
            "instructor_id": "instr",
            "specific_date": date(2025, 1, 13),
            "start_time": time(9, 0),
            "end_time": time(13, 0),
        }
    ]
