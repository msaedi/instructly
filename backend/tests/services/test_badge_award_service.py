from datetime import datetime, time, timedelta, timezone

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
