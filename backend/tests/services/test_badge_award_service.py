from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.auth import get_password_hash
from app.core.ulid_helper import generate_ulid
from app.models.badge import BadgeDefinition
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.review import Review, ReviewStatus
from app.models.service_catalog import InstructorService, ServiceCatalog, ServiceCategory
from app.models.user import User
from app.repositories.badge_repository import BadgeRepository
from app.services.badge_award_service import BadgeAwardService
from app.services.student_badge_service import StudentBadgeService

try:  # pragma: no cover - allow running from backend/ or repo root
    from backend.tests.factories.booking_builders import create_booking_pg_safe
except ModuleNotFoundError:  # pragma: no cover
    from tests.factories.booking_builders import create_booking_pg_safe


@pytest.fixture(scope="function")
def core_badges_seeded(db):
    from scripts.seed_data import BADGE_SEED_DEFINITIONS

    from app.models.badge import BadgeDefinition

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

    existing_slugs = {
        row_slug for (row_slug,) in db.query(BadgeDefinition.slug).all()
    }
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
    missing = expected_slugs - existing_slugs
    if missing:
        pytest.fail(
            "Core badge definitions missing in test session: "
            + ", ".join(sorted(missing))
        )

    return True


def _create_user(db, email: str) -> User:
    user = User(
        email=email,
        hashed_password=get_password_hash("TestPassword123!"),
        first_name=email.split("@")[0].split(".")[0].title(),
        last_name="Tester",
        zip_code="10001",
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def _get_or_create_category(db, *, slug: str, name: str, display_order: int = 1) -> ServiceCategory:
    category = db.query(ServiceCategory).filter(ServiceCategory.slug == slug).first()
    if category:
        return category

    category = ServiceCategory(
        id=generate_ulid(),
        name=name,
        slug=slug,
        display_order=display_order,
    )
    db.add(category)
    db.flush()
    return category


def _get_or_create_catalog(
    db,
    *,
    category: ServiceCategory,
    name: str,
    slug: str,
    description: str,
) -> ServiceCatalog:
    catalog = db.query(ServiceCatalog).filter(ServiceCatalog.slug == slug).first()
    if catalog:
        return catalog

    catalog = ServiceCatalog(
        id=generate_ulid(),
        category_id=category.id,
        name=name,
        slug=slug,
        description=description,
    )
    db.add(catalog)
    db.flush()
    return catalog


def _create_instructor_service(db, instructor: User, category_slug: str = "music") -> tuple[InstructorService, str]:
    category = _get_or_create_category(db, slug=category_slug, name="Music")
    catalog = _get_or_create_catalog(
        db,
        category=category,
        name="Piano Lessons",
        slug=f"piano-lessons-{category_slug}",
        description="Test piano lessons",
    )

    profile = InstructorProfile(user_id=instructor.id, is_live=True, bgc_status="passed")
    db.add(profile)
    db.flush()

    service = InstructorService(
        instructor_profile_id=profile.id,
        service_catalog_id=catalog.id,
        hourly_rate=50.0,
    )
    db.add(service)
    db.flush()
    return service, category.slug


_BOOKING_OFFSET_COUNTER = 0


def _create_booking(
    db,
    student: User,
    instructor: User,
    instructor_service: InstructorService,
    booked_at: datetime,
    completed_at: datetime,
) -> Booking:
    global _BOOKING_OFFSET_COUNTER
    offset_minutes = (_BOOKING_OFFSET_COUNTER * 3) % 180
    _BOOKING_OFFSET_COUNTER += 1

    booking = create_booking_pg_safe(
        db,
        student_id=student.id,
        instructor_id=instructor.id,
        instructor_service_id=instructor_service.id,
        booking_date=completed_at.date(),
        start_time=time(10, 0),
        end_time=time(11, 0),
        service_name="Piano Lessons",
        hourly_rate=50,
        total_price=50,
        duration_minutes=60,
        status=BookingStatus.CONFIRMED,
        offset_index=offset_minutes,
    )

    booking.status = BookingStatus.COMPLETED
    booking.confirmed_at = booked_at
    booking.completed_at = completed_at
    db.flush()
    return booking


def _create_review(
    db,
    *,
    booking: Booking,
    student: User,
    instructor: User,
    rating: int,
    created_at: datetime,
    status: ReviewStatus = ReviewStatus.PUBLISHED,
) -> Review:
    review = Review(
        booking_id=booking.id,
        student_id=student.id,
        instructor_id=instructor.id,
        instructor_service_id=booking.instructor_service_id,
        rating=rating,
        review_text="Great lesson",
        status=status,
        is_verified=True,
        booking_completed_at=booking.completed_at or created_at,
        created_at=created_at,
    )
    db.add(review)
    db.flush()
    return review


def test_milestone_badges_awarded_and_finalize(db, core_badges_seeded):
    student = _create_user(db, "student@example.com")
    instructor = _create_user(db, "instructor@example.com")
    instructor_service, category_slug = _create_instructor_service(db, instructor)

    badge_service = BadgeAwardService(db)
    repo = BadgeRepository(db)

    base_time = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)

    last_booking = None
    last_booked = None
    last_completed = None

    for i in range(10):
        booked_at = base_time + timedelta(days=i, hours=-4)
        completed_at = base_time + timedelta(days=i)
        booking = _create_booking(db, student, instructor, instructor_service, booked_at, completed_at)

        badge_service.check_and_award_on_lesson_completed(
            student_id=student.id,
            lesson_id=booking.id,
            instructor_id=instructor.id,
            category_slug=category_slug,
            booked_at_utc=booked_at,
            completed_at_utc=completed_at,
        )

        last_booking = booking
        last_booked = booked_at
        last_completed = completed_at

    # Welcome Aboard should start as pending (24h hold)
    awards = repo.list_student_badge_awards(student.id)
    welcome = next(a for a in awards if a["slug"] == "welcome_aboard")
    assert welcome["status"] == "pending"

    # Finalize after hold window
    summary = badge_service.finalize_pending_badges(base_time + timedelta(days=2))
    assert summary["confirmed"] == 1

    awards = repo.list_student_badge_awards(student.id)
    status_by_slug = {award["slug"]: award["status"] for award in awards}
    for slug in ["welcome_aboard", "foundation_builder", "first_steps", "dedicated_learner"]:
        assert status_by_slug[slug] == "confirmed"

    # Idempotency check
    count_before = len(awards)
    badge_service.check_and_award_on_lesson_completed(
        student_id=student.id,
        lesson_id=last_booking.id,
        instructor_id=instructor.id,
        category_slug=category_slug,
        booked_at_utc=last_booked,
        completed_at_utc=last_completed,
    )
    awards_after = repo.list_student_badge_awards(student.id)
    assert len(awards_after) == count_before


def test_momentum_starter_award(db, core_badges_seeded):
    student = _create_user(db, "momentum_student@example.com")
    instructor = _create_user(db, "momentum_instructor@example.com")
    instructor_service, category_slug = _create_instructor_service(db, instructor)

    badge_service = BadgeAwardService(db)
    repo = BadgeRepository(db)

    first_completed = datetime(2024, 2, 1, 15, 0, tzinfo=timezone.utc)
    first_booked = first_completed - timedelta(days=2)
    first_booking = _create_booking(db, student, instructor, instructor_service, first_booked, first_completed)

    badge_service.check_and_award_on_lesson_completed(
        student_id=student.id,
        lesson_id=first_booking.id,
        instructor_id=instructor.id,
        category_slug=category_slug,
        booked_at_utc=first_booked,
        completed_at_utc=first_completed,
    )

    second_booked = first_completed + timedelta(days=3)
    second_completed = second_booked + timedelta(days=2)
    second_booking = _create_booking(db, student, instructor, instructor_service, second_booked, second_completed)

    badge_service.check_and_award_on_lesson_completed(
        student_id=student.id,
        lesson_id=second_booking.id,
        instructor_id=instructor.id,
        category_slug=category_slug,
        booked_at_utc=second_booked,
        completed_at_utc=second_completed,
    )

    awards = repo.list_student_badge_awards(student.id)
    momentum = next(a for a in awards if a["slug"] == "momentum_starter")
    assert momentum["status"] == "confirmed"


def test_momentum_progress_first_and_second_lesson(db, core_badges_seeded):
    student = _create_user(db, "momentum_progress@example.com")
    instructor = _create_user(db, "momentum_progress_instr@example.com")
    instructor_service, category_slug = _create_instructor_service(db, instructor)

    badge_service = BadgeAwardService(db)
    repo = BadgeRepository(db)

    first_completed = datetime(2024, 4, 1, 15, 0, tzinfo=timezone.utc)
    first_booked = first_completed - timedelta(days=2)
    first_booking = _create_booking(db, student, instructor, instructor_service, first_booked, first_completed)

    badge_service.check_and_award_on_lesson_completed(
        student_id=student.id,
        lesson_id=first_booking.id,
        instructor_id=instructor.id,
        category_slug=category_slug,
        booked_at_utc=first_booked,
        completed_at_utc=first_completed,
    )

    progress_rows = repo.list_student_badge_progress(student.id)
    momentum_progress = next(p for p in progress_rows if p["slug"] == "momentum_starter")
    current_progress = momentum_progress["current_progress"]
    assert current_progress["current"] == 1
    assert current_progress["goal"] == 2
    assert current_progress["percent"] == 50
    assert current_progress["same_instructor"] is False
    assert current_progress["booked_within_window"] is False
    assert current_progress["completed_within_window"] is False

    second_booked = first_completed + timedelta(days=3)
    second_completed = second_booked + timedelta(days=2)
    second_booking = _create_booking(db, student, instructor, instructor_service, second_booked, second_completed)

    badge_service.check_and_award_on_lesson_completed(
        student_id=student.id,
        lesson_id=second_booking.id,
        instructor_id=instructor.id,
        category_slug=category_slug,
        booked_at_utc=second_booked,
        completed_at_utc=second_completed,
    )

    progress_rows = repo.list_student_badge_progress(student.id)
    momentum_progress = next(p for p in progress_rows if p["slug"] == "momentum_starter")
    current_progress = momentum_progress["current_progress"]
    assert current_progress["current"] == 2
    assert current_progress["goal"] == 2
    assert current_progress["percent"] == 100
    assert current_progress["same_instructor"] is True
    assert current_progress["booked_within_window"] is True
    assert current_progress["completed_within_window"] is True

    awards = repo.list_student_badge_awards(student.id)
    momentum_award = next(a for a in awards if a["slug"] == "momentum_starter")
    assert momentum_award["status"] == "confirmed"


def test_momentum_starter_not_awarded_when_outside_window(db, core_badges_seeded):
    student = _create_user(db, "momentum_late@example.com")
    instructor = _create_user(db, "momentum_late_instr@example.com")
    instructor_service, category_slug = _create_instructor_service(db, instructor)

    badge_service = BadgeAwardService(db)
    repo = BadgeRepository(db)

    first_completed = datetime(2024, 3, 1, 15, 0, tzinfo=timezone.utc)
    first_booking = _create_booking(
        db,
        student,
        instructor,
        instructor_service,
        first_completed - timedelta(days=2),
        first_completed,
    )

    badge_service.check_and_award_on_lesson_completed(
        student_id=student.id,
        lesson_id=first_booking.id,
        instructor_id=instructor.id,
        category_slug=category_slug,
        booked_at_utc=first_completed - timedelta(days=2),
        completed_at_utc=first_completed,
    )

    late_booked = first_completed + timedelta(days=10)
    late_completed = late_booked + timedelta(days=1)
    late_booking = _create_booking(
        db,
        student,
        instructor,
        instructor_service,
        late_booked,
        late_completed,
    )

    badge_service.check_and_award_on_lesson_completed(
        student_id=student.id,
        lesson_id=late_booking.id,
        instructor_id=instructor.id,
        category_slug=category_slug,
        booked_at_utc=late_booked,
        completed_at_utc=late_completed,
    )

    awards = repo.list_student_badge_awards(student.id)
    assert all(award["slug"] != "momentum_starter" for award in awards)
    progress_rows = repo.list_student_badge_progress(student.id)
    momentum_progress = next(p for p in progress_rows if p["slug"] == "momentum_starter")
    current_progress = momentum_progress["current_progress"]
    assert current_progress["current"] == 1
    assert current_progress["goal"] == 2
    assert current_progress["booked_within_window"] is False
    assert current_progress["completed_within_window"] is True


def test_finalize_pending_badges_revokes_when_criteria_fail(db, core_badges_seeded):
    student = _create_user(db, "pending_student@example.com")
    instructor = _create_user(db, "pending_instructor@example.com")
    instructor_service, category_slug = _create_instructor_service(db, instructor)

    badge_service = BadgeAwardService(db)
    repo = BadgeRepository(db)

    base_time = datetime(2024, 4, 1, 12, 0, tzinfo=timezone.utc)
    booking = _create_booking(
        db,
        student,
        instructor,
        instructor_service,
        base_time - timedelta(days=1),
        base_time,
    )

    badge_service.check_and_award_on_lesson_completed(
        student_id=student.id,
        lesson_id=booking.id,
        instructor_id=instructor.id,
        category_slug=category_slug,
        booked_at_utc=base_time - timedelta(days=1),
        completed_at_utc=base_time,
    )

    # Simulate lesson being invalidated before hold ends
    booking.status = BookingStatus.CANCELLED
    booking.completed_at = None
    db.flush()

    summary = badge_service.finalize_pending_badges(base_time + timedelta(days=2))
    assert summary["revoked"] == 1

    awards = repo.list_student_badge_awards(student.id)
    welcome = next(a for a in awards if a["slug"] == "welcome_aboard")
    assert welcome["status"] == "revoked"


def test_consistent_learner_awarded_after_three_weeks(db, core_badges_seeded):
    student = _create_user(db, "streak_student@example.com")
    student.timezone = "America/New_York"
    instructor = _create_user(db, "streak_instructor@example.com")
    instructor_service, category_slug = _create_instructor_service(db, instructor)
    db.flush()

    badge_service = BadgeAwardService(db)
    repo = BadgeRepository(db)

    base = datetime(2024, 1, 1, 15, 0, tzinfo=timezone.utc)
    completions = [base, base + timedelta(days=7), base + timedelta(days=14)]

    for completion in completions:
        booked = completion - timedelta(days=1)
        booking = _create_booking(db, student, instructor, instructor_service, booked, completion)
        badge_service.check_and_award_on_lesson_completed(
            student_id=student.id,
            lesson_id=booking.id,
            instructor_id=instructor.id,
            category_slug=category_slug,
            booked_at_utc=booked,
            completed_at_utc=completion,
        )

    progress = repo.list_student_badge_progress(student.id)
    consistent_progress = next(p for p in progress if p["slug"] == "consistent_learner")
    assert consistent_progress["current_progress"]["current"] >= 3
    assert consistent_progress["current_progress"]["percent"] == 100

    awards = repo.list_student_badge_awards(student.id)
    consistent_award = next(a for a in awards if a["slug"] == "consistent_learner")
    assert consistent_award["status"] == "confirmed"


def test_consistent_learner_awarded_with_grace_gap(db, core_badges_seeded):
    student = _create_user(db, "streak_grace@example.com")
    student.timezone = "America/New_York"
    instructor = _create_user(db, "streak_grace_instr@example.com")
    instructor_service, category_slug = _create_instructor_service(db, instructor)
    db.flush()

    badge_service = BadgeAwardService(db)
    repo = BadgeRepository(db)

    base = datetime(2024, 2, 1, 15, 0, tzinfo=timezone.utc)
    completions = [base, base + timedelta(days=8), base + timedelta(days=16)]

    for completion in completions:
        booked = completion - timedelta(days=1)
        booking = _create_booking(db, student, instructor, instructor_service, booked, completion)
        badge_service.check_and_award_on_lesson_completed(
            student_id=student.id,
            lesson_id=booking.id,
            instructor_id=instructor.id,
            category_slug=category_slug,
            booked_at_utc=booked,
            completed_at_utc=completion,
        )

    awards = repo.list_student_badge_awards(student.id)
    consistent_award = next(a for a in awards if a["slug"] == "consistent_learner")
    assert consistent_award["status"] == "confirmed"


def test_consistent_learner_not_awarded_when_gap_breaks(db, core_badges_seeded):
    student = _create_user(db, "streak_break@example.com")
    student.timezone = "America/New_York"
    instructor = _create_user(db, "streak_break_instr@example.com")
    instructor_service, category_slug = _create_instructor_service(db, instructor)
    db.flush()

    badge_service = BadgeAwardService(db)
    repo = BadgeRepository(db)

    base = datetime(2024, 3, 1, 15, 0, tzinfo=timezone.utc)
    completions = [base, base + timedelta(days=9), base + timedelta(days=18)]

    for completion in completions:
        booked = completion - timedelta(days=1)
        booking = _create_booking(db, student, instructor, instructor_service, booked, completion)
        badge_service.check_and_award_on_lesson_completed(
            student_id=student.id,
            lesson_id=booking.id,
            instructor_id=instructor.id,
            category_slug=category_slug,
            booked_at_utc=booked,
            completed_at_utc=completion,
        )

    awards = repo.list_student_badge_awards(student.id)
    streak_awards = [a for a in awards if a["slug"] == "consistent_learner"]
    assert not streak_awards or streak_awards[0]["status"] != "confirmed"


def _build_top_student_scenario(
    db,
    *,
    student_email: str,
    instructor_counts: dict[str, int],
    review_ratings: list[int],
    cancel_count: int = 0,
    noshow_count: int = 0,
) -> tuple[User, list[Review], BadgeAwardService, BadgeRepository, list[datetime]]:
    student = _create_user(db, student_email)
    student.timezone = "America/New_York"
    db.flush()

    completed_bookings: list[Booking] = []
    reviews: list[Review] = []
    badge_service = BadgeAwardService(db)
    repo = BadgeRepository(db)

    base_time = datetime(2024, 4, 1, 14, 0, tzinfo=timezone.utc)
    review_times: list[datetime] = []

    instructors = {}
    for idx, (category_slug, count) in enumerate(instructor_counts.items(), start=1):
        instructor = _create_user(db, f"top_instr_{idx}@example.com")
        service, _ = _create_instructor_service(db, instructor, category_slug=category_slug)
        for i in range(count):
            shift = idx * 10 + i
            booked = base_time + timedelta(days=shift, hours=-2)
            completed = base_time + timedelta(days=shift)
            booking = _create_booking(db, student, instructor, service, booked, completed)
            completed_bookings.append(booking)
        instructors[instructor.id] = (instructor, service)

    # Create cancellations / no-shows
    for i in range(cancel_count):
        instructor = list(instructors.values())[0][0]
        service = list(instructors.values())[0][1]
        shift = 100 + i
        booked = base_time + timedelta(days=shift)
        completed = booked + timedelta(hours=1)
        booking = _create_booking(db, student, instructor, service, booked, completed)
        booking.status = BookingStatus.CANCELLED
        booking.completed_at = None
        db.flush()

    for i in range(noshow_count):
        instructor = list(instructors.values())[0][0]
        service = list(instructors.values())[0][1]
        shift = 150 + i
        booked = base_time + timedelta(days=shift)
        completed = booked + timedelta(hours=1)
        booking = _create_booking(db, student, instructor, service, booked, completed)
        booking.status = BookingStatus.NO_SHOW
        booking.completed_at = None
        db.flush()

    # Attach reviews to the most recent completed bookings
    for rating in review_ratings:
        booking = completed_bookings.pop()
        instructor, _ = instructors[booking.instructor_id]
        created_at = booking.completed_at or base_time
        review = _create_review(
            db,
            booking=booking,
            student=student,
            instructor=instructor,
            rating=rating,
            created_at=created_at,
        )
        badge_service.check_and_award_on_review_received(
            student_id=student.id,
            review_id=review.id,
            created_at_utc=review.created_at,
        )
        reviews.append(review)
        review_times.append(review.created_at)

    return student, reviews, badge_service, repo, review_times


def test_top_student_award_pending_and_confirm(db, core_badges_seeded):
    instructor_counts = {"music": 6, "dance": 4}
    student, reviews, badge_service, repo, review_times = _build_top_student_scenario(
        db,
        student_email="top_student@example.com",
        instructor_counts=instructor_counts,
        review_ratings=[5, 5, 5],
    )

    awards = repo.list_student_badge_awards(student.id)
    top_award = next(a for a in awards if a["slug"] == "top_student")
    assert top_award["status"] == "pending"

    finalize_time = max(review_times) + timedelta(days=15)
    summary = badge_service.finalize_pending_badges(finalize_time)
    assert summary["confirmed"] >= 1

    awards = repo.list_student_badge_awards(student.id)
    top_award = next(a for a in awards if a["slug"] == "top_student")
    assert top_award["status"] == "confirmed"


def test_top_student_not_awarded_on_low_review_count(db, core_badges_seeded):
    instructor_counts = {"music": 6, "dance": 4}
    student, reviews, badge_service, repo, review_times = _build_top_student_scenario(
        db,
        student_email="top_student_low_reviews@example.com",
        instructor_counts=instructor_counts,
        review_ratings=[5, 5],
    )

    awards = [a for a in repo.list_student_badge_awards(student.id) if a["slug"] == "top_student"]
    assert not awards


def test_top_student_not_awarded_on_low_average(db, core_badges_seeded):
    instructor_counts = {"music": 6, "dance": 4}
    student, reviews, badge_service, repo, review_times = _build_top_student_scenario(
        db,
        student_email="top_student_low_avg@example.com",
        instructor_counts=instructor_counts,
        review_ratings=[5, 4, 5],
    )

    awards = [a for a in repo.list_student_badge_awards(student.id) if a["slug"] == "top_student"]
    assert not awards


def test_top_student_not_awarded_when_depth_criteria_fail(db, core_badges_seeded):
    definition = db.query(BadgeDefinition).filter(BadgeDefinition.slug == "top_student").first()
    original_config = dict(definition.criteria_config or {})
    updated_config = {**original_config, "distinct_instructors_min": 3, "or_single_instructor_min_lessons": 12}
    definition.criteria_config = updated_config
    db.flush()

    instructor_counts = {"music": 10}
    student, reviews, badge_service, repo, review_times = _build_top_student_scenario(
        db,
        student_email="top_student_depth_fail@example.com",
        instructor_counts=instructor_counts,
        review_ratings=[5, 5, 5],
    )

    awards = [a for a in repo.list_student_badge_awards(student.id) if a["slug"] == "top_student"]
    definition.criteria_config = original_config
    db.flush()
    assert not awards


def test_top_student_not_awarded_when_cancel_rate_high(db, core_badges_seeded):
    instructor_counts = {"music": 10}
    student, reviews, badge_service, repo, review_times = _build_top_student_scenario(
        db,
        student_email="top_student_cancel@example.com",
        instructor_counts=instructor_counts,
        review_ratings=[5, 5, 5],
        cancel_count=2,
    )

    awards = [a for a in repo.list_student_badge_awards(student.id) if a["slug"] == "top_student"]
    assert not awards


def test_top_student_revoked_when_metrics_drop(db, core_badges_seeded):
    instructor_counts = {"music": 6, "dance": 4}
    student, reviews, badge_service, repo, review_times = _build_top_student_scenario(
        db,
        student_email="top_student_revoke@example.com",
        instructor_counts=instructor_counts,
        review_ratings=[5, 5, 5],
    )

    awards = repo.list_student_badge_awards(student.id)
    top_award = next(a for a in awards if a["slug"] == "top_student")
    assert top_award["status"] == "pending"

    # Add a poor review to drop average below threshold
    instructor = _create_user(db, "top_revoke_instr@example.com")
    service, _ = _create_instructor_service(db, instructor, category_slug="vocal")
    booked = datetime(2024, 5, 1, 12, 0, tzinfo=timezone.utc)
    completed = booked + timedelta(hours=1)
    booking = _create_booking(db, student, instructor, service, booked, completed)
    bad_review = _create_review(
        db,
        booking=booking,
        student=student,
        instructor=instructor,
        rating=1,
        created_at=completed,
    )
    badge_service.check_and_award_on_review_received(
        student_id=student.id,
        review_id=bad_review.id,
        created_at_utc=bad_review.created_at,
    )

    finalize_time = max(review_times) + timedelta(days=15)
    summary = badge_service.finalize_pending_badges(finalize_time)
    assert summary["revoked"] >= 1

    awards = repo.list_student_badge_awards(student.id)
    top_award = next(a for a in awards if a["slug"] == "top_student")
    assert top_award["status"] == "revoked"


def _run_explorer_scenario(
    db,
    *,
    student_email: str,
    plan: list[dict],
) -> tuple[User, BadgeAwardService, BadgeRepository, list[Booking]]:
    student = _create_user(db, student_email)
    student.timezone = "America/New_York"
    db.flush()

    badge_service = BadgeAwardService(db)
    repo = BadgeRepository(db)
    bookings: list[Booking] = []

    instructor_cache: dict[str, tuple[User, InstructorService]] = {}

    def _get_resources(category_slug: str) -> tuple[User, InstructorService]:
        if category_slug in instructor_cache:
            return instructor_cache[category_slug]
        instructor = _create_user(db, f"explorer_{category_slug}_{len(instructor_cache)}@example.com")
        service, _ = _create_instructor_service(db, instructor, category_slug=category_slug)
        instructor_cache[category_slug] = (instructor, service)
        return instructor, service

    base_time = datetime(2024, 6, 1, 15, 0, tzinfo=timezone.utc)

    for idx, entry in enumerate(plan):
        category_slug = entry["category"]
        instructor, service = _get_resources(category_slug)
        booked = base_time + timedelta(days=idx * 2, hours=-2)
        completed = base_time + timedelta(days=idx * 2)
        booking = _create_booking(db, student, instructor, service, booked, completed)
        bookings.append(booking)

        badge_service.check_and_award_on_lesson_completed(
            student_id=student.id,
            lesson_id=booking.id,
            instructor_id=instructor.id,
            category_slug=category_slug,
            booked_at_utc=booked,
            completed_at_utc=completed,
        )

        if entry.get("create_review", True):
            _create_review(
                db,
                booking=booking,
                student=student,
                instructor=instructor,
                rating=entry.get("rating", 5),
                created_at=completed + timedelta(hours=1),
            )

    return student, badge_service, repo, bookings


def _get_explorer_award(repo: BadgeRepository, student_id: str):
    awards = repo.list_student_badge_awards(student_id)
    return next((a for a in awards if a["slug"] == "explorer"), None)


def _get_explorer_progress(repo: BadgeRepository, student_id: str):
    progress = repo.list_student_badge_progress(student_id)
    entry = next((p for p in progress if p["slug"] == "explorer"), None)
    return entry["current_progress"] if entry else None


def test_explorer_award_happy_path(db, core_badges_seeded):
    plan = [
        {"category": "music", "rating": 5},
        {"category": "music", "rating": 5},
        {"category": "dance", "rating": 5},
        {"category": "art", "rating": 5},
        {"category": "dance", "rating": 5},
    ]
    student, badge_service, repo, bookings = _run_explorer_scenario(
        db,
        student_email="explorer_happy@example.com",
        plan=plan,
    )

    award = _get_explorer_award(repo, student.id)
    assert award and award["status"] == "confirmed"

    progress = _get_explorer_progress(repo, student.id)
    assert progress["current"] >= 3
    assert progress["has_rebook"] is True
    assert progress["avg_rating"] >= 4.3


def test_explorer_not_awarded_when_breadth_insufficient(db, core_badges_seeded):
    plan = [
        {"category": "music", "rating": 5},
        {"category": "music", "rating": 5},
        {"category": "music", "rating": 5},
        {"category": "dance", "rating": 5},
        {"category": "dance", "rating": 5},
    ]
    student, badge_service, repo, bookings = _run_explorer_scenario(
        db,
        student_email="explorer_breadth@example.com",
        plan=plan,
    )

    assert _get_explorer_award(repo, student.id) is None


def test_explorer_not_awarded_without_rebook(db, core_badges_seeded):
    plan = [
        {"category": "music", "rating": 5},
        {"category": "dance", "rating": 5},
        {"category": "art", "rating": 5},
        {"category": "tech", "rating": 5},
        {"category": "science", "rating": 5},
    ]
    student, badge_service, repo, bookings = _run_explorer_scenario(
        db,
        student_email="explorer_norebook@example.com",
        plan=plan,
    )

    assert _get_explorer_award(repo, student.id) is None


def test_explorer_not_awarded_on_low_rating(db, core_badges_seeded):
    plan = [
        {"category": "music", "rating": 4},
        {"category": "music", "rating": 4},
        {"category": "dance", "rating": 4},
        {"category": "art", "rating": 4},
        {"category": "dance", "rating": 4},
    ]
    student, badge_service, repo, bookings = _run_explorer_scenario(
        db,
        student_email="explorer_low_rating@example.com",
        plan=plan,
    )

    assert _get_explorer_award(repo, student.id) is None


def test_explorer_progress_hidden_until_threshold(db, core_badges_seeded):
    plan = [
        {"category": "music", "rating": 5},
        {"category": "music", "rating": 5},
        {"category": "dance", "rating": 5},
        {"category": "art", "rating": 5},
    ]
    student, badge_service, repo, bookings = _run_explorer_scenario(
        db,
        student_email="explorer_visibility@example.com",
        plan=plan,
    )

    badge_service_api = StudentBadgeService(db)
    badges = badge_service_api.get_student_badges(student.id)
    explorer = next(entry for entry in badges if entry["slug"] == "explorer")
    assert explorer["progress"] is None

    # Add fifth completion to exceed show_after_total_lessons
    instructor = _create_user(db, "explorer_visibility_instr@example.com")
    service, category_slug = _create_instructor_service(db, instructor, category_slug="dance")
    booked = datetime(2024, 7, 1, 12, 0, tzinfo=timezone.utc)
    completed = booked + timedelta(hours=1)
    booking = _create_booking(db, student, instructor, service, booked, completed)
    badge_service.check_and_award_on_lesson_completed(
        student_id=student.id,
        lesson_id=booking.id,
        instructor_id=instructor.id,
        category_slug=category_slug,
        booked_at_utc=booked,
        completed_at_utc=completed,
    )
    _create_review(
        db,
        booking=booking,
        student=student,
        instructor=instructor,
        rating=5,
        created_at=completed + timedelta(hours=1),
    )

    badges = badge_service_api.get_student_badges(student.id)
    explorer = next(entry for entry in badges if entry["slug"] == "explorer")
    assert explorer["progress"] is not None


def test_badge_award_service_init_handles_missing_services(db, monkeypatch):
    import app.services.badge_award_service as badge_module

    class BoomCache:
        def __init__(self, *_args, **_kwargs) -> None:
            raise RuntimeError("cache down")

    class BoomNotification:
        def __init__(self, *_args, **_kwargs) -> None:
            raise RuntimeError("notify down")

    monkeypatch.setattr(badge_module, "CacheService", BoomCache)
    monkeypatch.setattr(badge_module, "NotificationService", BoomNotification)

    service = badge_module.BadgeAwardService(db)
    assert service.cache_service is None
    assert service.notification_service is None


def test_badge_award_service_maybe_notify_throttled(db, core_badges_seeded, monkeypatch):
    import app.services.badge_award_service as badge_module

    student = _create_user(db, "badge_notify_throttle@example.com")
    definition = db.query(BadgeDefinition).filter(BadgeDefinition.slug == "welcome_aboard").first()
    badge_service = BadgeAwardService(db)

    class DummyNotification:
        def __init__(self) -> None:
            self.calls = 0

        def send_badge_awarded_email(self, _user: User, _name: str) -> bool:
            self.calls += 1
            return True

    dummy = DummyNotification()
    badge_service.notification_service = dummy

    monkeypatch.setattr(
        badge_module, "can_send_now", lambda _user, _now, _cache: (False, "rate", "key")
    )
    record_calls: list[str] = []
    monkeypatch.setattr(
        badge_module, "record_send", lambda key, _cache: record_calls.append(key)
    )

    badge_service._maybe_notify_badge_awarded(
        student_id=student.id,
        badge_definition=definition,
        now_utc=datetime.now(timezone.utc),
    )

    assert dummy.calls == 0
    assert record_calls == []


def test_badge_award_service_maybe_notify_records_send(db, core_badges_seeded, monkeypatch):
    import app.services.badge_award_service as badge_module

    student = _create_user(db, "badge_notify_send@example.com")
    definition = db.query(BadgeDefinition).filter(BadgeDefinition.slug == "welcome_aboard").first()
    badge_service = BadgeAwardService(db)

    class DummyNotification:
        def __init__(self) -> None:
            self.calls = 0

        def send_badge_awarded_email(self, _user: User, _name: str) -> bool:
            self.calls += 1
            return True

    dummy = DummyNotification()
    badge_service.notification_service = dummy

    monkeypatch.setattr(
        badge_module, "can_send_now", lambda _user, _now, _cache: (True, None, "badge-key")
    )
    record_calls: list[str] = []
    monkeypatch.setattr(
        badge_module, "record_send", lambda key, _cache: record_calls.append(key)
    )

    badge_service._maybe_notify_badge_awarded(
        student_id=student.id,
        badge_definition=definition,
        now_utc=datetime.now(timezone.utc),
    )

    assert dummy.calls == 1
    assert record_calls == ["badge-key"]


def test_current_streak_length_handles_missing_and_invalid_timezone(db, core_badges_seeded):
    badge_service = BadgeAwardService(db)
    definition = db.query(BadgeDefinition).filter(BadgeDefinition.slug == "consistent_learner").first()

    assert badge_service._current_streak_length("missing-student", definition, goal=3) == 0

    student = _create_user(db, "streak_bad_tz@example.com")
    student.timezone = "Invalid/Zone"
    db.flush()
    assert badge_service._current_streak_length(student.id, definition, goal=3) == 0


def test_is_momentum_criteria_currently_met_true_and_false(db, core_badges_seeded):
    student = _create_user(db, "momentum_currently@example.com")
    instructor_a = _create_user(db, "momentum_currently_a@example.com")
    instructor_b = _create_user(db, "momentum_currently_b@example.com")
    service_a, _ = _create_instructor_service(db, instructor_a, category_slug="music")
    service_b, _ = _create_instructor_service(db, instructor_b, category_slug="dance")

    badge_service = BadgeAwardService(db)
    definition = db.query(BadgeDefinition).filter(BadgeDefinition.slug == "momentum_starter").first()

    base = datetime(2024, 8, 1, 12, 0, tzinfo=timezone.utc)
    _create_booking(db, student, instructor_a, service_a, base - timedelta(days=1), base)
    _create_booking(
        db,
        student,
        instructor_b,
        service_b,
        base + timedelta(days=1),
        base + timedelta(days=2),
    )

    assert badge_service._is_momentum_criteria_currently_met(definition, student.id) is False

    _create_booking(
        db,
        student,
        instructor_b,
        service_b,
        base + timedelta(days=3),
        base + timedelta(days=4),
    )

    assert badge_service._is_momentum_criteria_currently_met(definition, student.id) is True


def test_is_top_student_eligible_now_rejects_zero_goal(db):
    definition = BadgeDefinition(
        id=generate_ulid(),
        slug="top_student_zero_goal",
        name="Top Student Zero Goal",
        criteria_type="quality",
        criteria_config={
            "min_total_lessons": 0,
            "min_reviews": 0,
            "min_avg_rating": 0.0,
            "max_cancel_noshow_rate_pct_60d": 100.0,
            "distinct_instructors_min": 0,
            "or_single_instructor_min_lessons": 0,
        },
        is_active=True,
    )
    db.add(definition)
    db.flush()

    badge_service = BadgeAwardService(db)
    student = _create_user(db, "top_student_zero_goal@example.com")
    db.flush()

    assert (
        badge_service._is_top_student_eligible_now(
            student_id=student.id,
            now_utc=datetime.now(timezone.utc),
            definition=definition,
        )
        is False
    )


def test_is_explorer_eligible_now_blocks_without_rebook(db, core_badges_seeded):
    badge_service = BadgeAwardService(db)
    student = _create_user(db, "explorer_rebook_block@example.com")
    instructor = _create_user(db, "explorer_rebook_instr@example.com")
    service, _ = _create_instructor_service(db, instructor, category_slug="music")

    booked = datetime(2024, 9, 1, 12, 0, tzinfo=timezone.utc)
    completed = booked + timedelta(hours=1)
    _create_booking(db, student, instructor, service, booked, completed)

    definition = BadgeDefinition(
        id=generate_ulid(),
        slug="explorer_rebook_gate",
        name="Explorer Rebook Gate",
        criteria_type="exploration",
        criteria_config={
            "show_after_total_lessons": 1,
            "distinct_categories": 1,
            "min_overall_avg_rating": 0.0,
        },
        is_active=True,
    )
    db.add(definition)
    db.flush()

    assert badge_service._is_explorer_eligible_now(student.id, definition) is False


def test_is_explorer_eligible_now_blocks_on_min_avg(db, core_badges_seeded):
    badge_service = BadgeAwardService(db)
    student = _create_user(db, "explorer_min_avg@example.com")
    instructor = _create_user(db, "explorer_min_avg_instr@example.com")
    service, _ = _create_instructor_service(db, instructor, category_slug="music")

    base = datetime(2024, 10, 1, 12, 0, tzinfo=timezone.utc)
    _create_booking(db, student, instructor, service, base - timedelta(days=1), base)
    _create_booking(db, student, instructor, service, base + timedelta(days=1), base + timedelta(days=2))

    definition = BadgeDefinition(
        id=generate_ulid(),
        slug="explorer_min_avg_gate",
        name="Explorer Min Avg Gate",
        criteria_type="exploration",
        criteria_config={
            "show_after_total_lessons": 1,
            "distinct_categories": 1,
            "min_overall_avg_rating": 4.5,
        },
        is_active=True,
    )
    db.add(definition)
    db.flush()

    assert badge_service._is_explorer_eligible_now(student.id, definition) is False


def test_backfill_user_badges_awards_summary(db, core_badges_seeded):
    student = _create_user(db, "backfill_student@example.com")
    student.timezone = "America/New_York"

    instructor_music = _create_user(db, "backfill_instr_music@example.com")
    instructor_dance = _create_user(db, "backfill_instr_dance@example.com")
    instructor_art = _create_user(db, "backfill_instr_art@example.com")

    service_music, music_slug = _create_instructor_service(db, instructor_music, category_slug="music")
    service_dance, dance_slug = _create_instructor_service(db, instructor_dance, category_slug="dance")
    service_art, art_slug = _create_instructor_service(db, instructor_art, category_slug="art")

    services = [
        (service_music, instructor_music, music_slug),
        (service_music, instructor_music, music_slug),
        (service_dance, instructor_dance, dance_slug),
        (service_dance, instructor_dance, dance_slug),
        (service_art, instructor_art, art_slug),
        (service_art, instructor_art, art_slug),
        (service_music, instructor_music, music_slug),
        (service_dance, instructor_dance, dance_slug),
        (service_art, instructor_art, art_slug),
        (service_music, instructor_music, music_slug),
    ]

    base = datetime(2024, 11, 1, 12, 0, tzinfo=timezone.utc)
    offsets = [0, 1, 2, 7, 8, 9, 14, 15, 16, 17]
    completed_bookings: list[Booking] = []
    for idx, (service, instructor, _slug) in enumerate(services):
        completed_at = base + timedelta(days=offsets[idx])
        booked_at = completed_at - timedelta(days=1)
        booking = _create_booking(db, student, instructor, service, booked_at, completed_at)
        completed_bookings.append(booking)

    # Create high-rated reviews for quality badge window.
    for booking in completed_bookings[-3:]:
        instructor = db.query(User).filter(User.id == booking.instructor_id).first()
        _create_review(
            db,
            booking=booking,
            student=student,
            instructor=instructor,
            rating=5,
            created_at=(booking.completed_at or base) + timedelta(hours=1),
        )

    badge_service = BadgeAwardService(db)
    now_utc = base + timedelta(days=20)
    summary = badge_service.backfill_user_badges(
        student_id=student.id,
        now_utc=now_utc,
        send_notifications=False,
        dry_run=False,
    )

    assert summary["milestones"] >= 1
    assert summary["streak"] >= 1
    assert summary["explorer"] >= 1
    assert summary["quality_pending"] >= 1


def test_badge_award_service_init_with_injected_services(db):
    cache = object()
    notifier = object()
    service = BadgeAwardService(db, cache_service=cache, notification_service=notifier)
    assert service.cache_service is cache
    assert service.notification_service is notifier


def test_check_and_award_skips_inactive_and_zero_goal(db, core_badges_seeded):
    student = _create_user(db, "skip_goal_student@example.com")
    instructor = _create_user(db, "skip_goal_instructor@example.com")
    instructor_service, category_slug = _create_instructor_service(db, instructor)

    inactive = db.query(BadgeDefinition).filter(BadgeDefinition.slug == "welcome_aboard").first()
    inactive.is_active = False
    zero_goal = db.query(BadgeDefinition).filter(BadgeDefinition.slug == "foundation_builder").first()
    zero_goal.criteria_config = {"goal": 0}
    db.flush()

    badge_service = BadgeAwardService(db)
    repo = BadgeRepository(db)
    booked = datetime(2024, 12, 1, 10, 0, tzinfo=timezone.utc)
    completed = booked + timedelta(hours=1)
    booking = _create_booking(db, student, instructor, instructor_service, booked, completed)

    badge_service.check_and_award_on_lesson_completed(
        student_id=student.id,
        lesson_id=booking.id,
        instructor_id=instructor.id,
        category_slug=category_slug,
        booked_at_utc=booked,
        completed_at_utc=completed,
    )

    progress_slugs = {row["slug"] for row in repo.list_student_badge_progress(student.id)}
    assert "welcome_aboard" not in progress_slugs
    assert "foundation_builder" not in progress_slugs


def test_check_and_award_skips_momentum_progress_when_none(db, core_badges_seeded, monkeypatch):
    student = _create_user(db, "skip_momentum_student@example.com")
    instructor = _create_user(db, "skip_momentum_instructor@example.com")
    instructor_service, category_slug = _create_instructor_service(db, instructor)

    badge_service = BadgeAwardService(db)
    repo = BadgeRepository(db)
    monkeypatch.setattr(badge_service, "_build_momentum_progress_snapshot", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(badge_service, "_is_momentum_criteria_met_on_completion", lambda *_args, **_kwargs: False)

    booked = datetime(2024, 12, 2, 10, 0, tzinfo=timezone.utc)
    completed = booked + timedelta(hours=1)
    booking = _create_booking(db, student, instructor, instructor_service, booked, completed)

    badge_service.check_and_award_on_lesson_completed(
        student_id=student.id,
        lesson_id=booking.id,
        instructor_id=instructor.id,
        category_slug=category_slug,
        booked_at_utc=booked,
        completed_at_utc=completed,
    )

    progress_slugs = {row["slug"] for row in repo.list_student_badge_progress(student.id)}
    assert "momentum_starter" not in progress_slugs


def test_check_and_award_skips_consistent_and_explorer(db, core_badges_seeded):
    student = _create_user(db, "skip_consistent_student@example.com")
    instructor = _create_user(db, "skip_consistent_instructor@example.com")
    instructor_service, category_slug = _create_instructor_service(db, instructor)

    consistent = db.query(BadgeDefinition).filter(BadgeDefinition.slug == "consistent_learner").first()
    explorer = db.query(BadgeDefinition).filter(BadgeDefinition.slug == "explorer").first()
    consistent.is_active = False
    explorer.is_active = False
    db.flush()

    badge_service = BadgeAwardService(db)
    repo = BadgeRepository(db)
    booked = datetime(2024, 12, 3, 10, 0, tzinfo=timezone.utc)
    completed = booked + timedelta(hours=1)
    booking = _create_booking(db, student, instructor, instructor_service, booked, completed)

    badge_service.check_and_award_on_lesson_completed(
        student_id=student.id,
        lesson_id=booking.id,
        instructor_id=instructor.id,
        category_slug=category_slug,
        booked_at_utc=booked,
        completed_at_utc=completed,
    )

    progress_slugs = {row["slug"] for row in repo.list_student_badge_progress(student.id)}
    assert "consistent_learner" not in progress_slugs
    assert "explorer" not in progress_slugs


def test_award_according_to_hold_no_award_id(db, core_badges_seeded, monkeypatch):
    badge_service = BadgeAwardService(db)
    definition = db.query(BadgeDefinition).filter(BadgeDefinition.slug == "welcome_aboard").first()
    monkeypatch.setattr(
        badge_service.repository, "insert_award_pending_or_confirmed", lambda *_args, **_kwargs: None
    )
    badge_service._award_according_to_hold(
        "student-id", definition, {"current": 1, "goal": 1}, datetime.now(timezone.utc)
    )


def test_get_latest_completed_lesson_time_none(db, monkeypatch):
    badge_service = BadgeAwardService(db)
    monkeypatch.setattr(badge_service.repository, "get_latest_completed_lesson", lambda *_args, **_kwargs: None)
    result = badge_service._get_latest_completed_lesson_time(
        "student-id", datetime.now(timezone.utc), "lesson-id"
    )
    assert result is None


def test_build_momentum_progress_snapshot_missing_first_completed(db, monkeypatch):
    badge_service = BadgeAwardService(db)
    definition = BadgeDefinition(
        id=generate_ulid(),
        slug="momentum_missing_completed",
        name="Momentum Missing",
        criteria_type="velocity",
        criteria_config={"goal": 2},
        is_active=True,
    )
    monkeypatch.setattr(
        badge_service.repository,
        "get_latest_completed_lesson",
        lambda *_args, **_kwargs: {"completed_at": None, "instructor_id": "instr"},
    )
    booked = datetime(2024, 12, 4, 10, 0, tzinfo=timezone.utc)
    completed = booked + timedelta(hours=1)
    snapshot = badge_service._build_momentum_progress_snapshot(
        definition,
        "student-id",
        "instr",
        "lesson-id",
        booked,
        completed,
    )
    assert snapshot.get("first_completed_at") is None


def test_build_momentum_progress_snapshot_zero_windows(db, monkeypatch):
    badge_service = BadgeAwardService(db)
    definition = BadgeDefinition(
        id=generate_ulid(),
        slug="momentum_zero_windows",
        name="Momentum Zero",
        criteria_type="velocity",
        criteria_config={"goal": 2, "window_days_to_book": 0, "window_days_to_complete": 0},
        is_active=True,
    )
    first_completed = datetime(2024, 12, 5, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(
        badge_service.repository,
        "get_latest_completed_lesson",
        lambda *_args, **_kwargs: {"completed_at": first_completed, "instructor_id": "instr"},
    )
    booked = first_completed + timedelta(days=1)
    completed = booked + timedelta(hours=1)
    snapshot = badge_service._build_momentum_progress_snapshot(
        definition,
        "student-id",
        "instr",
        "lesson-id",
        booked,
        completed,
    )
    assert snapshot["booked_within_window"] is True
    assert snapshot["completed_within_window"] is True
    assert snapshot["eligible_pair"] is True


def test_build_momentum_progress_snapshot_out_of_order_times(db, monkeypatch):
    badge_service = BadgeAwardService(db)
    definition = BadgeDefinition(
        id=generate_ulid(),
        slug="momentum_out_of_order",
        name="Momentum Out",
        criteria_type="velocity",
        criteria_config={"goal": 2, "window_days_to_book": 3, "window_days_to_complete": 3},
        is_active=True,
    )
    first_completed = datetime(2024, 12, 6, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(
        badge_service.repository,
        "get_latest_completed_lesson",
        lambda *_args, **_kwargs: {"completed_at": first_completed, "instructor_id": "instr"},
    )
    booked = first_completed - timedelta(days=1)
    completed = booked - timedelta(hours=1)
    snapshot = badge_service._build_momentum_progress_snapshot(
        definition,
        "student-id",
        "instr",
        "lesson-id",
        booked,
        completed,
    )
    assert snapshot["booked_within_window"] is False
    assert snapshot["completed_within_window"] is False


def test_is_student_currently_eligible_branches(db, monkeypatch):
    badge_service = BadgeAwardService(db)
    now = datetime(2024, 12, 7, 10, 0, tzinfo=timezone.utc)

    milestone_def = BadgeDefinition(
        id=generate_ulid(),
        slug="milestone_zero",
        name="Milestone Zero",
        criteria_type="milestone",
        criteria_config={"counts": "completed_lessons", "goal": 0},
        is_active=True,
    )
    assert badge_service._is_student_currently_eligible("student-id", milestone_def, now) is False

    velocity_def = BadgeDefinition(
        id=generate_ulid(),
        slug="velocity",
        name="Velocity",
        criteria_type="velocity",
        criteria_config={},
        is_active=True,
    )
    monkeypatch.setattr(badge_service, "_is_momentum_criteria_currently_met", lambda *_a, **_k: True)
    assert badge_service._is_student_currently_eligible("student-id", velocity_def, now) is True

    exploration_def = BadgeDefinition(
        id=generate_ulid(),
        slug="explore",
        name="Explore",
        criteria_type="exploration",
        criteria_config={},
        is_active=True,
    )
    monkeypatch.setattr(badge_service, "_is_explorer_eligible_now", lambda *_a, **_k: True)
    assert badge_service._is_student_currently_eligible("student-id", exploration_def, now) is True

    streak_def = BadgeDefinition(
        id=generate_ulid(),
        slug="streak",
        name="Streak",
        criteria_type="streak",
        criteria_config={"goal": 2},
        is_active=True,
    )
    monkeypatch.setattr(badge_service, "_current_streak_length", lambda *_a, **_k: 2)
    assert badge_service._is_student_currently_eligible("student-id", streak_def, now) is True

    other_def = BadgeDefinition(
        id=generate_ulid(),
        slug="other",
        name="Other",
        criteria_type="other",
        criteria_config={},
        is_active=True,
    )
    assert badge_service._is_student_currently_eligible("student-id", other_def, now) is True


def test_is_momentum_criteria_met_on_completion_branches(db, monkeypatch):
    badge_service = BadgeAwardService(db)
    definition = BadgeDefinition(
        id=generate_ulid(),
        slug="momentum_branch",
        name="Momentum Branch",
        criteria_type="velocity",
        criteria_config={},
        is_active=True,
    )
    now = datetime(2024, 12, 8, 10, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(badge_service.repository, "get_latest_completed_lesson", lambda *_a, **_k: None)
    assert (
        badge_service._is_momentum_criteria_met_on_completion(
            definition, "student-id", "instr", "lesson", now, now
        )
        is False
    )

    monkeypatch.setattr(
        badge_service.repository,
        "get_latest_completed_lesson",
        lambda *_a, **_k: {"completed_at": None, "instructor_id": "instr"},
    )
    assert (
        badge_service._is_momentum_criteria_met_on_completion(
            definition, "student-id", "instr", "lesson", now, now
        )
        is False
    )

    monkeypatch.setattr(
        badge_service.repository,
        "get_latest_completed_lesson",
        lambda *_a, **_k: {"completed_at": now, "instructor_id": "instr"},
    )
    definition.criteria_config = {"same_instructor_required": True}
    assert (
        badge_service._is_momentum_criteria_met_on_completion(
            definition, "student-id", "other", "lesson", now, now + timedelta(hours=1)
        )
        is False
    )

    definition.criteria_config = {}
    assert (
        badge_service._is_momentum_criteria_met_on_completion(
            definition, "student-id", "instr", "lesson", now - timedelta(days=1), now
        )
        is False
    )

    definition.criteria_config = {"window_days_to_book": 1}
    assert (
        badge_service._is_momentum_criteria_met_on_completion(
            definition, "student-id", "instr", "lesson", now + timedelta(days=2), now + timedelta(days=2, hours=1)
        )
        is False
    )

    definition.criteria_config = {"window_days_to_complete": 1}
    assert (
        badge_service._is_momentum_criteria_met_on_completion(
            definition, "student-id", "instr", "lesson", now + timedelta(days=1), now + timedelta(days=3)
        )
        is False
    )


def test_evaluate_consistent_learner_early_returns(db, monkeypatch):
    badge_service = BadgeAwardService(db)
    definition = BadgeDefinition(
        id=generate_ulid(),
        slug="consistent_test",
        name="Consistent",
        criteria_type="streak",
        criteria_config={"goal": 3},
        is_active=True,
    )
    badge_service._evaluate_consistent_learner(
        definition, student_id="missing-student", completed_at_utc=datetime.now(timezone.utc)
    )

    student = _create_user(db, "consistent_timezone@example.com")
    student.timezone = "America/New_York"
    db.flush()

    monkeypatch.setattr("app.services.badge_award_service.get_user_timezone", lambda _u: None)
    badge_service._evaluate_consistent_learner(
        definition, student_id=student.id, completed_at_utc=datetime.now(timezone.utc)
    )


def test_evaluate_consistent_learner_no_completion_times(db, core_badges_seeded, monkeypatch):
    badge_service = BadgeAwardService(db)
    definition = db.query(BadgeDefinition).filter(BadgeDefinition.slug == "consistent_learner").first()
    student = _create_user(db, "consistent_empty@example.com")
    student.timezone = "America/New_York"
    db.flush()

    monkeypatch.setattr("app.services.badge_award_service.get_user_timezone", lambda _u: timezone.utc)
    monkeypatch.setattr(badge_service.repository, "list_completed_lesson_times", lambda *_a, **_k: [])
    badge_service._evaluate_consistent_learner(
        definition, student_id=student.id, completed_at_utc=datetime.now(timezone.utc)
    )


def test_current_streak_length_no_completions(db, monkeypatch):
    badge_service = BadgeAwardService(db)
    definition = BadgeDefinition(
        id=generate_ulid(),
        slug="streak_empty",
        name="Streak Empty",
        criteria_type="streak",
        criteria_config={"goal": 3},
        is_active=True,
    )
    student = _create_user(db, "streak_empty@example.com")
    student.timezone = "America/New_York"
    db.flush()

    monkeypatch.setattr("app.services.badge_award_service.get_user_timezone", lambda _u: timezone.utc)
    monkeypatch.setattr(badge_service.repository, "list_completed_lesson_times", lambda *_a, **_k: [])
    assert badge_service._current_streak_length(student.id, definition, goal=3) == 0


def test_maybe_notify_badge_awarded_missing_notification(db, core_badges_seeded):
    badge_service = BadgeAwardService(db)
    badge_service.notification_service = None
    definition = db.query(BadgeDefinition).filter(BadgeDefinition.slug == "welcome_aboard").first()
    badge_service._maybe_notify_badge_awarded(
        student_id="student-id",
        badge_definition=definition,
        now_utc=datetime.now(timezone.utc),
    )


def test_maybe_notify_badge_awarded_missing_email(db, core_badges_seeded):
    badge_service = BadgeAwardService(db)

    class DummyNotification:
        def send_badge_awarded_email(self, _user: User, _name: str) -> bool:
            return True

    badge_service.user_repository.get_by_id = lambda *_args, **_kwargs: SimpleNamespace(email=None)

    badge_service.notification_service = DummyNotification()
    definition = db.query(BadgeDefinition).filter(BadgeDefinition.slug == "welcome_aboard").first()
    badge_service._maybe_notify_badge_awarded(
        student_id="student-id",
        badge_definition=definition,
        now_utc=datetime.now(timezone.utc),
    )


def test_is_momentum_criteria_currently_met_branches(db, monkeypatch):
    badge_service = BadgeAwardService(db)
    definition = BadgeDefinition(
        id=generate_ulid(),
        slug="momentum_loop",
        name="Momentum Loop",
        criteria_type="velocity",
        criteria_config={},
        is_active=True,
    )
    base = datetime(2024, 12, 9, 10, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(
        badge_service.repository,
        "list_completed_lessons",
        lambda *_a, **_k: [{"completed_at": base, "booked_at": base, "instructor_id": "i1"}],
    )
    assert badge_service._is_momentum_criteria_currently_met(definition, "student-id") is False

    definition.criteria_config = {"same_instructor_required": True}
    monkeypatch.setattr(
        badge_service.repository,
        "list_completed_lessons",
        lambda *_a, **_k: [
            {"completed_at": base, "booked_at": base, "instructor_id": "i1"},
            {"completed_at": base + timedelta(days=1), "booked_at": base + timedelta(days=1), "instructor_id": "i2"},
        ],
    )
    assert badge_service._is_momentum_criteria_currently_met(definition, "student-id") is False

    definition.criteria_config = {}
    monkeypatch.setattr(
        badge_service.repository,
        "list_completed_lessons",
        lambda *_a, **_k: [
            {"completed_at": base, "booked_at": base, "instructor_id": "i1"},
            {"completed_at": base + timedelta(days=1), "booked_at": base - timedelta(days=1), "instructor_id": "i1"},
        ],
    )
    assert badge_service._is_momentum_criteria_currently_met(definition, "student-id") is False

    definition.criteria_config = {"window_days_to_book": 1}
    monkeypatch.setattr(
        badge_service.repository,
        "list_completed_lessons",
        lambda *_a, **_k: [
            {"completed_at": base, "booked_at": base, "instructor_id": "i1"},
            {"completed_at": base + timedelta(days=3), "booked_at": base + timedelta(days=3), "instructor_id": "i1"},
        ],
    )
    assert badge_service._is_momentum_criteria_currently_met(definition, "student-id") is False

    definition.criteria_config = {"window_days_to_complete": 1}
    monkeypatch.setattr(
        badge_service.repository,
        "list_completed_lessons",
        lambda *_a, **_k: [
            {"completed_at": base, "booked_at": base, "instructor_id": "i1"},
            {
                "completed_at": base + timedelta(days=3),
                "booked_at": base + timedelta(days=1),
                "instructor_id": "i1",
            },
        ],
    )
    assert badge_service._is_momentum_criteria_currently_met(definition, "student-id") is False


def test_is_top_student_eligible_now_min_lessons(db, monkeypatch):
    badge_service = BadgeAwardService(db)
    definition = BadgeDefinition(
        id=generate_ulid(),
        slug="top_min_lessons",
        name="Top Min Lessons",
        criteria_type="quality",
        criteria_config={"min_total_lessons": 2, "min_reviews": 0, "min_avg_rating": 0.0},
        is_active=True,
    )
    monkeypatch.setattr(badge_service.repository, "count_completed_lessons", lambda *_a, **_k: 0)
    assert (
        badge_service._is_top_student_eligible_now(
            "student-id", datetime.now(timezone.utc), definition
        )
        is False
    )


def test_is_explorer_eligible_now_branches(db, monkeypatch):
    badge_service = BadgeAwardService(db)
    definition = BadgeDefinition(
        id=generate_ulid(),
        slug="explorer_eligible",
        name="Explorer Eligible",
        criteria_type="exploration",
        criteria_config={"show_after_total_lessons": 2, "distinct_categories": 2, "min_overall_avg_rating": 4.0},
        is_active=True,
    )

    monkeypatch.setattr(badge_service.repository, "count_completed_lessons", lambda *_a, **_k: 1)
    assert badge_service._is_explorer_eligible_now("student-id", definition) is False

    monkeypatch.setattr(badge_service.repository, "count_completed_lessons", lambda *_a, **_k: 3)
    monkeypatch.setattr(badge_service.repository, "count_distinct_completed_categories", lambda *_a, **_k: 1)
    monkeypatch.setattr(badge_service.repository, "has_rebook_in_any_category", lambda *_a, **_k: True)
    monkeypatch.setattr(badge_service.repository, "get_overall_student_avg_rating", lambda *_a, **_k: 5.0)
    assert badge_service._is_explorer_eligible_now("student-id", definition) is False

    monkeypatch.setattr(badge_service.repository, "count_distinct_completed_categories", lambda *_a, **_k: 2)
    assert badge_service._is_explorer_eligible_now("student-id", definition) is True
