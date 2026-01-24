from datetime import datetime, timedelta, timezone

from app.models.instructor import InstructorProfile
from app.repositories.instructor_lifecycle_repository import InstructorLifecycleRepository


def test_record_event_creates_row(db, test_instructor):
    repo = InstructorLifecycleRepository(db)

    event = repo.record_event(
        user_id=test_instructor.id,
        event_type="registered",
        metadata={"is_founding": True},
    )

    assert event.user_id == test_instructor.id
    assert event.event_type == "registered"
    assert event.metadata_json["is_founding"] is True


def test_get_latest_event_for_user(db, test_instructor):
    repo = InstructorLifecycleRepository(db)

    now = datetime.now(timezone.utc)
    first = repo.record_event(user_id=test_instructor.id, event_type="registered")
    first.occurred_at = now - timedelta(days=2)

    second = repo.record_event(user_id=test_instructor.id, event_type="profile_submitted")
    second.occurred_at = now - timedelta(days=1)

    db.flush()

    latest = repo.get_latest_event_for_user(test_instructor.id)
    assert latest is not None
    assert latest.event_type == "profile_submitted"


def test_get_events_for_user_with_filter(db, test_instructor):
    repo = InstructorLifecycleRepository(db)

    repo.record_event(user_id=test_instructor.id, event_type="registered")
    repo.record_event(user_id=test_instructor.id, event_type="profile_submitted")
    repo.record_event(user_id=test_instructor.id, event_type="services_configured")

    all_events = repo.get_events_for_user(test_instructor.id)
    assert len(all_events) == 3

    filtered = repo.get_events_for_user(
        test_instructor.id, event_types=["profile_submitted", "services_configured"]
    )
    assert {event.event_type for event in filtered} == {
        "profile_submitted",
        "services_configured",
    }


def test_get_current_stage_ignores_non_milestones(db, test_instructor):
    repo = InstructorLifecycleRepository(db)

    now = datetime.now(timezone.utc)
    first = repo.record_event(user_id=test_instructor.id, event_type="registered")
    first.occurred_at = now - timedelta(days=3)
    second = repo.record_event(user_id=test_instructor.id, event_type="profile_submitted")
    second.occurred_at = now - timedelta(days=2)
    paused = repo.record_event(user_id=test_instructor.id, event_type="paused")
    paused.occurred_at = now - timedelta(days=1)
    db.flush()

    stage = repo.get_current_stage(test_instructor.id)
    assert stage == "profile_submitted"


def test_count_by_stage_with_filters(db, test_instructor, test_instructor_2):
    repo = InstructorLifecycleRepository(db)
    now = datetime.now(timezone.utc)

    event1 = repo.record_event(user_id=test_instructor.id, event_type="registered")
    event1.occurred_at = now - timedelta(days=10)

    event2 = repo.record_event(user_id=test_instructor_2.id, event_type="registered")
    event2.occurred_at = now - timedelta(days=1)

    db.flush()

    counts = repo.count_by_stage(start_date=now - timedelta(days=5))
    assert counts["registered"] == 1

    profile = (
        db.query(InstructorProfile)
        .filter(InstructorProfile.user_id == test_instructor.id)
        .first()
    )
    assert profile is not None
    profile.is_founding_instructor = True
    db.flush()

    founding_counts = repo.count_by_stage(founding_only=True)
    assert founding_counts["registered"] == 1


def test_get_stuck_instructors(db, test_instructor, test_instructor_2):
    repo = InstructorLifecycleRepository(db)
    now = datetime.now(timezone.utc)

    old_event = repo.record_event(user_id=test_instructor.id, event_type="profile_submitted")
    old_event.occurred_at = now - timedelta(days=10)

    recent_event = repo.record_event(user_id=test_instructor_2.id, event_type="profile_submitted")
    recent_event.occurred_at = now - timedelta(days=1)

    db.flush()

    stuck = repo.get_stuck_instructors(stuck_days=7)
    stuck_ids = {row["user_id"] for row in stuck}

    assert test_instructor.id in stuck_ids
    assert test_instructor_2.id not in stuck_ids
    assert all(row["days_stuck"] >= 7 for row in stuck if row["user_id"] == test_instructor.id)
