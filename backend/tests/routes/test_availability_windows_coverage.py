from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from fastapi import HTTPException, Request, Response
import pytest

from app.core.exceptions import DomainException
from app.routes.v1 import availability_windows as routes
from app.schemas.availability_window import (
    ApplyToDateRangeRequest,
    AvailabilityWindowUpdate,
    BlackoutDateCreate,
    BulkUpdateRequest,
    CopyWeekRequest,
    ValidateWeekRequest,
    WeekSpecificScheduleCreate,
)
from app.services.availability_service import AvailabilityService


def _make_request() -> Request:
    return Request({"type": "http", "headers": []})


def _next_monday() -> date:
    today = date.today()
    offset = (7 - today.weekday()) % 7
    if offset == 0:
        offset = 7
    return today + timedelta(days=offset)


def test_get_week_availability_domain_and_unexpected_errors(test_instructor):
    class DomainFailService:
        def get_week_bits(self, *_args, **_kwargs):
            raise DomainException("boom")

    class BoomService:
        def get_week_bits(self, *_args, **_kwargs):
            raise RuntimeError("boom")

    response = Response()
    with pytest.raises(HTTPException) as exc:
        routes.get_week_availability(
            response=response,
            start_date=date.today(),
            current_user=test_instructor,
            availability_service=DomainFailService(),
        )
    assert exc.value.status_code == 500

    response = Response()
    with pytest.raises(HTTPException) as exc:
        routes.get_week_availability(
            response=response,
            start_date=date.today(),
            current_user=test_instructor,
            availability_service=BoomService(),
        )
    assert exc.value.status_code == 500


def test_save_week_availability_parses_date_time_objects(db, test_instructor):
    week_start = _next_monday()
    payload = WeekSpecificScheduleCreate(
        week_start=week_start,
        clear_existing=True,
        schedule=[
            {
                "date": week_start.isoformat(),
                "start_time": "09:00",
                "end_time": "10:00",
            }
        ],
    )

    result = routes.save_week_availability(
        request=_make_request(),
        response=Response(),
        payload=payload,
        current_user=test_instructor,
        availability_service=AvailabilityService(db),
        override=False,
    )

    assert result.week_start == week_start
    assert result.days_written >= 1


def test_save_week_availability_invalid_schedule_returns_500(db, test_instructor):
    from app.schemas.availability_window import ScheduleItem

    payload = WeekSpecificScheduleCreate.model_construct(
        schedule=[
            ScheduleItem.model_construct(date=None, start_time="09:00", end_time="10:00"),
            ScheduleItem.model_construct(date="bad-date", start_time="09:00", end_time="10:00"),
        ],
        clear_existing=True,
        week_start=None,
        base_version=None,
        version=None,
        override=False,
    )

    with pytest.raises(HTTPException) as exc:
        routes.save_week_availability(
            request=_make_request(),
            response=Response(),
            payload=payload,
            current_user=test_instructor,
            availability_service=AvailabilityService(db),
            override=False,
        )
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_copy_week_availability_metadata_fallbacks(test_instructor):
    class StubWeekService:
        async def copy_week_availability(self, *_args, **_kwargs):
            return {"_metadata": {"message": None}, "windows_created": "3"}

    week_start = _next_monday()
    payload = CopyWeekRequest(
        from_week_start=week_start,
        to_week_start=week_start + timedelta(days=7),
    )

    result = await routes.copy_week_availability(
        payload=payload,
        current_user=test_instructor,
        week_operation_service=StubWeekService(),
    )

    assert result.message == "Week copied successfully"
    assert result.windows_copied == 3


@pytest.mark.asyncio
async def test_apply_to_date_range_coerces_bad_numbers(test_instructor):
    class StubWeekService:
        async def apply_pattern_to_date_range(self, *_args, **_kwargs):
            return {
                "message": "ok",
                "windows_created": "bad",
                "weeks_applied": "2",
                "weeks_affected": None,
                "days_written": "bad",
                "skipped_past_targets": "bad",
                "edited_dates": [date(2025, 1, 1)],
                "dates_processed": "bad",
                "dates_with_windows": "bad",
                "dates_with_slots": "bad",
                "written_dates": ["2025-01-01"],
            }

    week_start = _next_monday()
    payload = ApplyToDateRangeRequest(
        from_week_start=week_start,
        start_date=week_start,
        end_date=week_start + timedelta(days=14),
    )

    result = await routes.apply_to_date_range(
        payload=payload,
        current_user=test_instructor,
        week_operation_service=StubWeekService(),
    )

    assert result.weeks_applied == 2
    assert result.windows_created == 0
    assert result.days_written == 0


@pytest.mark.asyncio
async def test_deprecated_availability_endpoints_raise(test_instructor):
    update_payload = AvailabilityWindowUpdate.model_construct()
    with pytest.raises(HTTPException) as exc:
        routes.update_availability_window(
            window_id="w1",
            payload=update_payload,
            current_user=test_instructor,
            availability_service=None,
        )
    assert exc.value.status_code == 501

    with pytest.raises(HTTPException) as exc:
        routes.delete_availability_window(
            window_id="w1",
            current_user=test_instructor,
            availability_service=None,
        )
    assert exc.value.status_code == 501

    bulk_payload = BulkUpdateRequest.model_construct(operations=[])
    with pytest.raises(HTTPException) as exc:
        await routes.bulk_update_availability(
            update_data=bulk_payload,
            current_user=test_instructor,
            bulk_operation_service=None,
        )
    assert exc.value.status_code == 410


def test_get_all_availability_success_and_errors(test_instructor):
    class SuccessService:
        def get_all_instructor_availability(self, *_args, **_kwargs):
            return [
                {
                    "id": "slot-1",
                    "instructor_id": test_instructor.id,
                    "specific_date": date.today(),
                    "start_time": time(9, 0),
                    "end_time": time(10, 0),
                }
            ]

    result = routes.get_all_availability(
        start_date=None,
        end_date=None,
        current_user=test_instructor,
        availability_service=SuccessService(),
    )
    assert result[0].id == "slot-1"

    class DomainFailService:
        def get_all_instructor_availability(self, *_args, **_kwargs):
            raise DomainException("boom")

    with pytest.raises(HTTPException) as exc:
        routes.get_all_availability(
            start_date=None,
            end_date=None,
            current_user=test_instructor,
            availability_service=DomainFailService(),
        )
    assert exc.value.status_code == 500

    class BoomService:
        def get_all_instructor_availability(self, *_args, **_kwargs):
            raise RuntimeError("boom")

    with pytest.raises(HTTPException) as exc:
        routes.get_all_availability(
            start_date=None,
            end_date=None,
            current_user=test_instructor,
            availability_service=BoomService(),
        )
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_get_week_booked_slots_success_and_errors(test_instructor):
    class SuccessConflictChecker:
        def get_booked_times_for_week(self, *_args, **_kwargs):
            return {date.today().isoformat(): [{"start_time": time(9, 0), "end_time": time(10, 0)}]}

    class SuccessPresentation:
        def format_booked_slots_from_service_data(self, booked_slots_by_date):
            # Return list of BookedSlotItem-compatible dicts
            return [
                {
                    "booking_id": "01K2MAY484FQGFEQVN3VKGYZ58",
                    "date": next(iter(booked_slots_by_date.keys())),
                    "start_time": "09:00:00",
                    "end_time": "10:00:00",
                    "student_first_name": "John",
                    "student_last_initial": "D",
                    "service_name": "Piano Lesson",
                    "service_area_short": "UES",
                    "duration_minutes": 60,
                    "location_type": "student_location",
                }
            ]

    start_date = _next_monday()
    result = await routes.get_week_booked_slots(
        start_date=start_date,
        current_user=test_instructor,
        conflict_checker=SuccessConflictChecker(),
        presentation_service=SuccessPresentation(),
    )
    assert result.week_end == start_date + timedelta(days=6)

    class DomainConflictChecker:
        def get_booked_times_for_week(self, *_args, **_kwargs):
            raise DomainException("boom")

    with pytest.raises(HTTPException) as exc:
        await routes.get_week_booked_slots(
            start_date=start_date,
            current_user=test_instructor,
            conflict_checker=DomainConflictChecker(),
            presentation_service=SuccessPresentation(),
        )
    assert exc.value.status_code == 500

    class BoomConflictChecker:
        def get_booked_times_for_week(self, *_args, **_kwargs):
            raise RuntimeError("boom")

    with pytest.raises(HTTPException) as exc:
        await routes.get_week_booked_slots(
            start_date=start_date,
            current_user=test_instructor,
            conflict_checker=BoomConflictChecker(),
            presentation_service=SuccessPresentation(),
        )
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_validate_week_changes_success_and_errors(test_instructor):
    class SuccessBulkService:
        def validate_week_changes(self, *_args, **_kwargs):
            return {
                "valid": True,
                "summary": {
                    "total_operations": 1,
                    "valid_operations": 1,
                    "invalid_operations": 0,
                    "operations_by_type": {"add": 1},
                    "has_conflicts": False,
                    "estimated_changes": {"slots_added": 1, "slots_removed": 0},
                },
                "details": [
                    {
                        "operation_index": 0,
                        "action": "add",
                        "date": date.today(),
                        "start_time": time(9, 0),
                        "end_time": time(10, 0),
                    }
                ],
                "warnings": [],
            }

    payload = ValidateWeekRequest(
        current_week={_next_monday().isoformat(): []},
        saved_week={_next_monday().isoformat(): []},
        week_start=_next_monday(),
    )
    result = await routes.validate_week_changes(
        validation_data=payload,
        current_user=test_instructor,
        bulk_operation_service=SuccessBulkService(),
    )
    assert result.valid is True

    class DomainBulkService:
        def validate_week_changes(self, *_args, **_kwargs):
            raise DomainException("boom")

    with pytest.raises(HTTPException) as exc:
        await routes.validate_week_changes(
            validation_data=payload,
            current_user=test_instructor,
            bulk_operation_service=DomainBulkService(),
        )
    assert exc.value.status_code == 500

    class BoomBulkService:
        def validate_week_changes(self, *_args, **_kwargs):
            raise RuntimeError("boom")

    with pytest.raises(HTTPException) as exc:
        await routes.validate_week_changes(
            validation_data=payload,
            current_user=test_instructor,
            bulk_operation_service=BoomBulkService(),
        )
    assert exc.value.status_code == 500


def test_blackout_date_endpoints_success_and_errors(test_instructor):
    class SuccessService:
        def get_blackout_dates(self, *_args, **_kwargs):
            return [
                {
                    "id": "b1",
                    "instructor_id": test_instructor.id,
                    "date": date.today(),
                    "reason": "Vacation",
                    "created_at": datetime.now(timezone.utc),
                }
            ]

        def add_blackout_date(self, *_args, **_kwargs):
            return {
                "id": "b2",
                "instructor_id": test_instructor.id,
                "date": date.today(),
                "reason": "Holiday",
                "created_at": datetime.now(timezone.utc),
            }

        def delete_blackout_date(self, *_args, **_kwargs):
            return None

    result = routes.get_blackout_dates(
        current_user=test_instructor,
        availability_service=SuccessService(),
    )
    assert result[0].id == "b1"

    payload = BlackoutDateCreate(date=date.today(), reason="Holiday")
    added = routes.add_blackout_date(
        blackout_data=payload,
        current_user=test_instructor,
        availability_service=SuccessService(),
    )
    assert added.id == "b2"

    deleted = routes.delete_blackout_date(
        blackout_id="b2",
        current_user=test_instructor,
        availability_service=SuccessService(),
    )
    assert deleted.blackout_id == "b2"

    class DomainService:
        def get_blackout_dates(self, *_args, **_kwargs):
            raise DomainException("boom")

        def add_blackout_date(self, *_args, **_kwargs):
            raise DomainException("boom")

        def delete_blackout_date(self, *_args, **_kwargs):
            raise DomainException("boom")

    with pytest.raises(HTTPException) as exc:
        routes.get_blackout_dates(
            current_user=test_instructor,
            availability_service=DomainService(),
        )
    assert exc.value.status_code == 500

    with pytest.raises(HTTPException) as exc:
        routes.add_blackout_date(
            blackout_data=payload,
            current_user=test_instructor,
            availability_service=DomainService(),
        )
    assert exc.value.status_code == 500

    with pytest.raises(HTTPException) as exc:
        routes.delete_blackout_date(
            blackout_id="b2",
            current_user=test_instructor,
            availability_service=DomainService(),
        )
    assert exc.value.status_code == 500

    class BoomService:
        def get_blackout_dates(self, *_args, **_kwargs):
            raise RuntimeError("boom")

        def add_blackout_date(self, *_args, **_kwargs):
            raise RuntimeError("boom")

        def delete_blackout_date(self, *_args, **_kwargs):
            raise RuntimeError("boom")

    with pytest.raises(HTTPException) as exc:
        routes.get_blackout_dates(
            current_user=test_instructor,
            availability_service=BoomService(),
        )
    assert exc.value.status_code == 500

    with pytest.raises(HTTPException) as exc:
        routes.add_blackout_date(
            blackout_data=payload,
            current_user=test_instructor,
            availability_service=BoomService(),
        )
    assert exc.value.status_code == 500

    with pytest.raises(HTTPException) as exc:
        routes.delete_blackout_date(
            blackout_id="b2",
            current_user=test_instructor,
            availability_service=BoomService(),
        )
    assert exc.value.status_code == 500
