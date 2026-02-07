from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from tests.services import test_badge_award_service as award_helpers

from app.core.ulid_helper import generate_ulid
from app.models.badge import BadgeDefinition
from app.repositories.badge_repository import BadgeRepository
from app.services.badge_award_service import BadgeAwardService


class _CacheStub(SimpleNamespace):
    def get(self, _key):  # pragma: no cover - simple stub
        return 0

    def set(self, *_args, **_kwargs):  # pragma: no cover - simple stub
        return None


@pytest.fixture
def core_badges_seeded(db):
    from scripts.seed_data import BADGE_SEED_DEFINITIONS

    for payload in BADGE_SEED_DEFINITIONS:
        slug = payload["slug"]
        existing = db.query(BadgeDefinition).filter(BadgeDefinition.slug == slug).first()
        if existing:
            existing.name = payload["name"]
            existing.description = payload.get("description")
            existing.criteria_type = payload.get("criteria_type")
            existing.criteria_config = payload.get("criteria_config")
            existing.icon_key = payload.get("icon_key")
            existing.display_order = payload.get("display_order")
            existing.is_active = payload.get("is_active", True)
        else:
            badge = BadgeDefinition(
                id=generate_ulid(),
                slug=slug,
                name=payload["name"],
                description=payload.get("description"),
                criteria_type=payload.get("criteria_type"),
                criteria_config=payload.get("criteria_config"),
                icon_key=payload.get("icon_key"),
                display_order=payload.get("display_order"),
                is_active=payload.get("is_active", True),
            )
            db.add(badge)

    db.flush()

    expected_slugs = {
        "welcome_aboard",
        "foundation_builder",
        "first_steps",
        "dedicated_learner",
        "momentum_starter",
        "consistent_learner",
        "top_student",
        "explorer",
        "favorite_partnership",
        "year_one_learner",
    }
    existing_slugs = {row_slug for (row_slug,) in db.query(BadgeDefinition.slug).all()}
    missing = expected_slugs - existing_slugs
    if missing:
        pytest.fail(
            "Core badge definitions missing in test session: " + ", ".join(sorted(missing))
        )

    return True


def _build_service(db):
    notification_mock = Mock()
    cache_stub = _CacheStub()
    service = BadgeAwardService(
        db,
        notification_service=notification_mock,
        cache_service=cache_stub,
    )
    return service, notification_mock


def _create_instructor_bundle(db, slug_suffix: str):
    instructor = award_helpers._create_user(db, f"instructor_{slug_suffix}@example.com")
    service, category_name = award_helpers._create_instructor_service(
        db, instructor, category_name=f"{slug_suffix}_category"
    )
    return instructor, service, category_name


def _complete_lesson(
    db,
    *,
    student,
    instructor,
    instructor_service,
    booked_at: datetime,
    completed_at: datetime,
    add_review: bool = False,
    rating: int = 5,
):
    booking = award_helpers._create_booking(
        db,
        student=student,
        instructor=instructor,
        instructor_service=instructor_service,
        booked_at=booked_at,
        completed_at=completed_at,
    )
    if add_review:
        award_helpers._create_review(
            db,
            booking=booking,
            student=student,
            instructor=instructor,
            rating=rating,
            created_at=completed_at + timedelta(hours=2),
        )
    return booking


def test_backfill_milestones_and_explorer_idempotent(db, core_badges_seeded):
    service, notification_mock = _build_service(db)
    repo = BadgeRepository(db)
    student = award_helpers._create_user(db, "backfill.student@example.com")
    now = datetime(2024, 5, 1, 15, tzinfo=timezone.utc)

    instructors = [_create_instructor_bundle(db, slug) for slug in ("alpha", "beta", "gamma")]

    # Ten completed lessons, spread across 3 categories with a rebook.
    for idx in range(10):
        instructor, instructor_service, _category = instructors[idx % len(instructors)]
        completed_at = now - timedelta(days=idx % 5)
        _complete_lesson(
            db,
            student=student,
            instructor=instructor,
            instructor_service=instructor_service,
            booked_at=completed_at - timedelta(days=1),
            completed_at=completed_at,
            add_review=idx < 2,  # only two reviews to keep explorer eligible but avoid quality badge
        )

    summary_dry = service.backfill_user_badges(student.id, now, dry_run=True)
    assert summary_dry["dry_run"] is True
    assert summary_dry["milestones"] == 4
    assert summary_dry["explorer"] == 1
    assert repo.list_student_badge_awards(student.id) == []

    summary_award = service.backfill_user_badges(student.id, now)
    assert summary_award["milestones"] == 4
    assert summary_award["explorer"] == 1
    assert summary_award["skipped_existing"] == 0

    awarded_slugs = {row["slug"] for row in repo.list_student_badge_awards(student.id)}
    assert awarded_slugs.issuperset(
        {"welcome_aboard", "foundation_builder", "first_steps", "dedicated_learner", "explorer"}
    )
    notification_mock.send_badge_awarded_email.assert_not_called()

    summary_again = service.backfill_user_badges(student.id, now)
    assert summary_again["milestones"] == 0
    assert summary_again["explorer"] == 0
    assert summary_again["skipped_existing"] == 5  # previously created awards
    assert len(repo.list_student_badge_awards(student.id)) == 5


def test_backfill_streak_award_once(db, core_badges_seeded):
    service, _notification_mock = _build_service(db)
    repo = BadgeRepository(db)
    student = award_helpers._create_user(db, "streak.student@example.com")
    now = datetime(2024, 3, 3, 17, tzinfo=timezone.utc)

    instructor, instructor_service, _ = _create_instructor_bundle(db, "streak")
    # Three consecutive weekly completions (local timezone defaults to America/New_York).
    for weeks_ago in (21, 14, 7):
        completed_at = now - timedelta(days=weeks_ago)
        _complete_lesson(
            db,
            student=student,
            instructor=instructor,
            instructor_service=instructor_service,
            booked_at=completed_at - timedelta(days=1),
            completed_at=completed_at,
            add_review=False,
        )

    summary_first = service.backfill_user_badges(student.id, now)
    assert summary_first["streak"] == 1

    awards = [row for row in repo.list_student_badge_awards(student.id) if row["slug"] == "consistent_learner"]
    assert len(awards) == 1

    summary_second = service.backfill_user_badges(student.id, now)
    assert summary_second["streak"] == 0
    awards_again = [row for row in repo.list_student_badge_awards(student.id) if row["slug"] == "consistent_learner"]
    assert len(awards_again) == 1


def test_backfill_quality_pending_only(db, core_badges_seeded):
    service, notification_mock = _build_service(db)
    repo = BadgeRepository(db)
    student = award_helpers._create_user(db, "quality.student@example.com")
    now = datetime(2024, 6, 1, 18, tzinfo=timezone.utc)

    instructor_a, service_a, _ = _create_instructor_bundle(db, "quality_a")
    instructor_b, service_b, _ = _create_instructor_bundle(db, "quality_b")
    instructors = [(instructor_a, service_a), (instructor_b, service_b)]

    for idx in range(10):
        instructor, instructor_service = instructors[idx % 2]
        completed_at = now - timedelta(days=idx * 2 + 1)
        _complete_lesson(
            db,
            student=student,
            instructor=instructor,
            instructor_service=instructor_service,
            booked_at=completed_at - timedelta(days=1),
            completed_at=completed_at,
            add_review=True,
            rating=5,
        )

    summary = service.backfill_user_badges(student.id, now)
    assert summary["quality_pending"] == 1

    awards = repo.list_student_badge_awards(student.id)
    top_student = next(row for row in awards if row["slug"] == "top_student")
    assert top_student["status"] == "pending"
    notification_mock.send_badge_awarded_email.assert_not_called()

    summary_again = service.backfill_user_badges(student.id, now)
    assert summary_again["quality_pending"] == 0
    awards_again = [row for row in repo.list_student_badge_awards(student.id) if row["slug"] == "top_student"]
    assert len(awards_again) == 1


def test_backfill_no_activity_no_awards(db, core_badges_seeded):
    service, _notification_mock = _build_service(db)
    repo = BadgeRepository(db)
    student = award_helpers._create_user(db, "inactive.student@example.com")
    now = datetime(2024, 4, 1, 12, tzinfo=timezone.utc)

    summary = service.backfill_user_badges(student.id, now)
    assert summary["milestones"] == 0
    assert summary["streak"] == 0
    assert summary["explorer"] == 0
    assert summary["quality_pending"] == 0
    assert summary["skipped_existing"] == 0
    assert repo.list_student_badge_awards(student.id) == []
