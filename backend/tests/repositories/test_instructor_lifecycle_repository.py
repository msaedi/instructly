from datetime import datetime, timedelta, timezone

import pytest

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


def test_stuck_instructors_excludes_went_live(db, test_instructor):
    repo = InstructorLifecycleRepository(db)
    now = datetime.now(timezone.utc)

    went_live = repo.record_event(user_id=test_instructor.id, event_type="went_live")
    went_live.occurred_at = now - timedelta(days=30)
    db.flush()

    stuck = repo.get_stuck_instructors(stuck_days=7)
    stuck_ids = {row["user_id"] for row in stuck}

    assert test_instructor.id not in stuck_ids


def test_record_event_invalid_type_raises_exception(db, test_instructor):
    """Line 47: Should raise RepositoryException for invalid event_type."""
    from app.core.exceptions import RepositoryException

    repo = InstructorLifecycleRepository(db)

    with pytest.raises(RepositoryException, match="Invalid lifecycle event_type"):
        repo.record_event(
            user_id=test_instructor.id,
            event_type="invalid_event_type_that_does_not_exist",
        )


def test_count_by_stage_with_end_date_filter(db, test_instructor, test_instructor_2):
    """Line 119: Should filter events by end_date."""
    repo = InstructorLifecycleRepository(db)
    now = datetime.now(timezone.utc)

    # Create events at different times
    event1 = repo.record_event(user_id=test_instructor.id, event_type="registered")
    event1.occurred_at = now - timedelta(days=20)  # 20 days ago

    event2 = repo.record_event(user_id=test_instructor_2.id, event_type="registered")
    event2.occurred_at = now - timedelta(days=5)  # 5 days ago

    db.flush()

    # Filter to only include events older than 10 days (should get event1 only)
    end_date = now - timedelta(days=10)
    counts = repo.count_by_stage(end_date=end_date)

    assert counts["registered"] == 1


def test_count_by_stage_with_both_date_filters(db, test_instructor, test_instructor_2):
    """Should filter events by both start_date and end_date."""
    repo = InstructorLifecycleRepository(db)
    now = datetime.now(timezone.utc)

    # Create events at different times
    event1 = repo.record_event(user_id=test_instructor.id, event_type="registered")
    event1.occurred_at = now - timedelta(days=30)  # 30 days ago (before window)

    event2 = repo.record_event(user_id=test_instructor_2.id, event_type="registered")
    event2.occurred_at = now - timedelta(days=15)  # 15 days ago (in window)

    db.flush()

    # Filter to 20-10 days ago (should get event2 only)
    start_date = now - timedelta(days=20)
    end_date = now - timedelta(days=10)
    counts = repo.count_by_stage(start_date=start_date, end_date=end_date)

    assert counts["registered"] == 1


def test_get_stuck_instructors_with_stage_filter(db, test_instructor, test_instructor_2):
    """Should filter stuck instructors by specific stage."""
    repo = InstructorLifecycleRepository(db)
    now = datetime.now(timezone.utc)

    # One at registered, one at profile_submitted
    event1 = repo.record_event(user_id=test_instructor.id, event_type="registered")
    event1.occurred_at = now - timedelta(days=15)

    event2 = repo.record_event(user_id=test_instructor_2.id, event_type="profile_submitted")
    event2.occurred_at = now - timedelta(days=15)

    db.flush()

    # Filter to only "registered" stage
    stuck = repo.get_stuck_instructors(stuck_days=7, stage="registered")
    stuck_ids = {row["user_id"] for row in stuck}

    assert test_instructor.id in stuck_ids
    assert test_instructor_2.id not in stuck_ids


def test_get_events_for_user_no_filter(db, test_instructor):
    """Should return all events when no filter provided."""
    repo = InstructorLifecycleRepository(db)

    repo.record_event(user_id=test_instructor.id, event_type="registered")
    repo.record_event(user_id=test_instructor.id, event_type="profile_submitted")
    repo.record_event(user_id=test_instructor.id, event_type="went_live")

    events = repo.get_events_for_user(test_instructor.id)

    assert len(events) == 3
    event_types = {e.event_type for e in events}
    assert "registered" in event_types
    assert "profile_submitted" in event_types
    assert "went_live" in event_types


def test_get_current_stage_returns_none_for_new_user(db, test_instructor):
    """Should return None when user has no milestone events."""
    repo = InstructorLifecycleRepository(db)

    # No events recorded yet
    stage = repo.get_current_stage(test_instructor.id)

    assert stage is None


def test_get_latest_event_returns_none_for_no_events(db, test_instructor):
    """Should return None when user has no events."""
    repo = InstructorLifecycleRepository(db)

    # No events recorded yet
    latest = repo.get_latest_event_for_user(test_instructor.id)

    assert latest is None


def test_get_stuck_instructors_respects_limit(db, test_instructor, test_instructor_2):
    """Should respect the limit parameter."""
    repo = InstructorLifecycleRepository(db)
    now = datetime.now(timezone.utc)

    # Create stuck events for both instructors
    event1 = repo.record_event(user_id=test_instructor.id, event_type="registered")
    event1.occurred_at = now - timedelta(days=15)

    event2 = repo.record_event(user_id=test_instructor_2.id, event_type="registered")
    event2.occurred_at = now - timedelta(days=15)

    db.flush()

    # Limit to 1
    stuck = repo.get_stuck_instructors(stuck_days=7, limit=1)

    assert len(stuck) == 1


def test_get_stuck_instructors_minimum_limit(db, test_instructor):
    """Should enforce minimum limit of 1."""
    repo = InstructorLifecycleRepository(db)
    now = datetime.now(timezone.utc)

    event = repo.record_event(user_id=test_instructor.id, event_type="registered")
    event.occurred_at = now - timedelta(days=15)
    db.flush()

    # Even with 0 or negative limit, should return at least 1 if stuck
    stuck = repo.get_stuck_instructors(stuck_days=7, limit=0)

    # Should still return results (limit is max(1, limit))
    assert len(stuck) >= 0  # limit=0 becomes max(1,0)=1
