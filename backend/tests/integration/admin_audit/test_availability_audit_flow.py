from datetime import date, timedelta

import pytest

from app.schemas.availability_window import CopyWeekRequest, WeekSpecificScheduleCreate
from app.services.availability_service import AvailabilityService
from app.services.week_operation_service import WeekOperationService


def _upcoming_monday() -> date:
    today = date.today()
    offset = (7 - today.weekday()) % 7
    return today + timedelta(days=offset)


@pytest.mark.asyncio
async def test_availability_audit_flow(
    db,
    client,
    test_instructor,
    auth_headers_admin,
    auth_headers_student,
):
    availability_service = AvailabilityService(db)
    week_service = WeekOperationService(db, availability_service=availability_service)

    monday = _upcoming_monday()
    tuesday = monday + timedelta(days=1)

    schedule = [
        {"date": monday.isoformat(), "start_time": "09:00", "end_time": "10:00"},
        {"date": tuesday.isoformat(), "start_time": "14:00", "end_time": "15:30"},
    ]

    request = WeekSpecificScheduleCreate(
        schedule=schedule,
        clear_existing=True,
        week_start=monday,
    )

    await availability_service.save_week_availability(
        test_instructor.id,
        request,
        actor=test_instructor,
    )

    copy_request = CopyWeekRequest(
        from_week_start=monday,
        to_week_start=monday + timedelta(days=7),
    )

    await week_service.copy_week_availability(
        test_instructor.id,
        copy_request.from_week_start,
        copy_request.to_week_start,
        actor=test_instructor,
    )

    params = {"entity_type": "availability", "actor_id": test_instructor.id, "limit": 10}
    response = client.get("/api/admin/audit", params=params, headers=auth_headers_admin)
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2

    actions = [entry["action"] for entry in payload["items"]]
    assert actions[0] == "copy_week"
    assert actions[1] == "save_week"

    for entry in payload["items"]:
        assert "slot_counts" in (entry.get("after") or {})
        assert entry["actor_role"] == "instructor"

    forbidden = client.get("/api/admin/audit", headers=auth_headers_student)
    assert forbidden.status_code == 403
