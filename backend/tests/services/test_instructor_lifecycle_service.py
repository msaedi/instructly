from datetime import datetime, timedelta, timezone

from app.repositories.instructor_lifecycle_repository import InstructorLifecycleRepository
from app.services.instructor_lifecycle_service import InstructorLifecycleService


def test_record_methods_create_events(db, test_instructor):
    service = InstructorLifecycleService(db)
    service.record_registration(test_instructor.id, is_founding=True)
    service.record_profile_submitted(test_instructor.id)
    service.record_services_configured(test_instructor.id)
    service.record_bgc_initiated(test_instructor.id)
    service.record_bgc_completed(test_instructor.id, status="passed")
    service.record_went_live(test_instructor.id)

    repo = InstructorLifecycleRepository(db)
    events = repo.get_events_for_user(test_instructor.id)
    types = {event.event_type for event in events}

    assert "registered" in types
    assert "profile_submitted" in types
    assert "services_configured" in types
    assert "bgc_initiated" in types
    assert "bgc_completed" in types
    assert "went_live" in types

    bgc_event = next(event for event in events if event.event_type == "bgc_completed")
    assert bgc_event.metadata_json["status"] == "passed"


def test_get_funnel_summary_conversion_rates(db, test_instructor, test_instructor_2):
    service = InstructorLifecycleService(db)

    service.record_registration(test_instructor.id)
    service.record_profile_submitted(test_instructor.id)

    service.record_registration(test_instructor_2.id)

    summary = service.get_funnel_summary()
    stages = {stage["stage"]: stage["count"] for stage in summary["stages"]}

    assert stages["registered"] == 2
    assert stages["profile_submitted"] == 1

    conversion_rates = {
        (rate["from_stage"], rate["to_stage"]): rate["rate"]
        for rate in summary["conversion_rates"]
    }
    assert conversion_rates[("registered", "profile_submitted")] == 0.5


def test_get_stuck_instructors(db, test_instructor, test_instructor_2):
    service = InstructorLifecycleService(db)

    service.record_registration(test_instructor.id)
    service.record_registration(test_instructor_2.id)

    repo = InstructorLifecycleRepository(db)
    old_event = repo.get_latest_event_for_user(test_instructor.id)
    recent_event = repo.get_latest_event_for_user(test_instructor_2.id)

    assert old_event is not None
    assert recent_event is not None

    now = datetime.now(timezone.utc)
    old_event.occurred_at = now - timedelta(days=10)
    recent_event.occurred_at = now - timedelta(days=1)
    db.flush()

    payload = service.get_stuck_instructors(stuck_days=7)

    stuck_ids = {row["user_id"] for row in payload["instructors"]}
    assert test_instructor.id in stuck_ids
    assert test_instructor_2.id not in stuck_ids
    assert payload["total_stuck"] == 1
