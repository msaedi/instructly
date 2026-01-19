from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pydantic import SecretStr
import pytest
import pytz

from app.auth import get_password_hash
from app.core.config import settings
from app.core.enums import PermissionName, RoleName
from app.core.exceptions import ValidationException
from app.models.booking import BookingStatus
from app.models.instructor import InstructorProfile
from app.models.user import User
from app.repositories.payment_repository import PaymentRepository
from app.services.permission_service import PermissionService
from app.services.review_service import ReviewService
from tests.conftest import unique_email
from tests.factories.booking_builders import create_booking_pg_safe


class DummyCache:
    def __init__(self) -> None:
        self.data: dict[str, object] = {}
        self.deleted: list[str] = []

    def get(self, key: str):
        return self.data.get(key)

    def set(self, key: str, value: object, ttl: int | None = None) -> None:
        self.data[key] = value

    def delete(self, key: str) -> None:
        self.deleted.append(key)


def _complete_booking(db, booking, *, days_ago: int = 1) -> None:
    booking.status = BookingStatus.COMPLETED
    booking.completed_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
    db.flush()


def _create_student(db, test_password: str) -> User:
    student = User(
        email=unique_email("review.student"),
        hashed_password=get_password_hash(test_password),
        first_name="Alt",
        last_name="Student",
        zip_code="10001",
        is_active=True,
    )
    db.add(student)
    db.flush()
    permission_service = PermissionService(db)
    permission_service.assign_role(student.id, RoleName.STUDENT)
    permission_service.grant_permission(student.id, PermissionName.CREATE_BOOKINGS.value)
    db.refresh(student)
    return student


def _get_instructor_profile(db, instructor_id: str) -> InstructorProfile:
    profile = (
        db.query(InstructorProfile)
        .filter(InstructorProfile.user_id == instructor_id)
        .first()
    )
    if profile is None:
        raise RuntimeError("Expected instructor profile to exist")
    return profile


def test_submit_review_confirmed_future_date_blocks(db, test_booking, monkeypatch):
    tz = pytz.timezone("America/New_York")
    fake_now = tz.localize(datetime.combine(date.today(), time(9, 0)))
    monkeypatch.setattr(
        "app.core.timezone_utils.get_user_now_by_id",
        lambda user_id, db_session: fake_now,
    )

    test_booking.status = BookingStatus.CONFIRMED
    test_booking.completed_at = None
    test_booking.booking_date = date.today() + timedelta(days=1)
    db.flush()

    service = ReviewService(db)
    with pytest.raises(ValidationException):
        service.submit_review(
            student_id=test_booking.student_id,
            booking_id=test_booking.id,
            rating=5,
        )


def test_submit_review_confirmed_same_day_before_end_blocks(db, test_booking, monkeypatch):
    tz = pytz.timezone("America/New_York")
    fake_now = tz.localize(datetime.combine(date.today(), time(8, 0)))
    monkeypatch.setattr(
        "app.core.timezone_utils.get_user_now_by_id",
        lambda user_id, db_session: fake_now,
    )

    test_booking.status = BookingStatus.CONFIRMED
    test_booking.completed_at = None
    test_booking.booking_date = date.today()
    test_booking.end_time = time(10, 0)
    db.flush()

    service = ReviewService(db)
    with pytest.raises(ValidationException):
        service.submit_review(
            student_id=test_booking.student_id,
            booking_id=test_booking.id,
            rating=5,
        )


def test_submit_review_confirmed_after_end_allows_and_notifies(db, test_booking, monkeypatch):
    tz = pytz.timezone("America/New_York")
    fake_now = tz.localize(datetime.combine(date.today(), time(18, 0)))
    monkeypatch.setattr(
        "app.core.timezone_utils.get_user_now_by_id",
        lambda user_id, db_session: fake_now,
    )

    test_booking.status = BookingStatus.CONFIRMED
    test_booking.completed_at = None
    test_booking.booking_date = date.today()
    test_booking.end_time = time(10, 0)
    db.flush()

    cache = DummyCache()
    notifier = MagicMock()
    service = ReviewService(db, cache=cache, notification_service=notifier)

    review = service.submit_review(
        student_id=test_booking.student_id,
        booking_id=test_booking.id,
        rating=5,
        review_text="Nice lesson",
    )

    assert review.id is not None
    assert notifier.notify_user_best_effort.called
    assert cache.deleted


def test_submit_review_falls_back_when_user_time_lookup_fails(db, test_booking, monkeypatch):
    def _raise(*args, **kwargs):
        raise RuntimeError("tz lookup failed")

    monkeypatch.setattr("app.core.timezone_utils.get_user_now_by_id", _raise)

    test_booking.status = BookingStatus.CONFIRMED
    test_booking.completed_at = None
    test_booking.booking_date = date.today() - timedelta(days=1)
    db.flush()

    service = ReviewService(db)
    review = service.submit_review(
        student_id=test_booking.student_id,
        booking_id=test_booking.id,
        rating=5,
    )

    assert review.id is not None


def test_submit_review_long_text_notification_failure_is_non_blocking(db, test_booking):
    class FailingNotifier:
        def notify_user_best_effort(self, **kwargs):
            raise RuntimeError("notify failed")

    _complete_booking(db, test_booking)
    service = ReviewService(db, notification_service=FailingNotifier())

    review = service.submit_review(
        student_id=test_booking.student_id,
        booking_id=test_booking.id,
        rating=5,
        review_text="x" * 150,
    )

    assert review.id is not None


def test_submit_review_with_tip_requires_payment_method_when_no_default(db, test_booking):
    _complete_booking(db, test_booking)
    payment_repo = PaymentRepository(db)
    payment_repo.create_customer_record(test_booking.student_id, "cus_review_tip")
    instructor_profile = _get_instructor_profile(db, test_booking.instructor_id)
    payment_repo.create_connected_account_record(instructor_profile.id, "acct_tip_ready")
    db.commit()

    service = ReviewService(db)
    with patch(
        "app.services.review_service.StripeService.create_payment_intent",
        return_value=SimpleNamespace(
            stripe_payment_intent_id="pi_tip",
            status="requires_confirmation",
        ),
    ):
        result = service.submit_review_with_tip(
            student_id=test_booking.student_id,
            booking_id=test_booking.id,
            rating=5,
            review_text="Great",
            tip_amount_cents=500,
        )

    assert result["tip_status"] == "requires_payment_method"
    assert result["tip_client_secret"] is None


def test_submit_review_with_tip_missing_instructor_profile_raises(db, test_booking):
    _complete_booking(db, test_booking)
    new_instructor = User(
        email=unique_email("review.tip.no_profile"),
        hashed_password=get_password_hash("test-password"),
        first_name="No",
        last_name="Profile",
        zip_code="10001",
        is_active=True,
    )
    db.add(new_instructor)
    db.flush()
    test_booking.instructor_id = new_instructor.id
    db.flush()

    service = ReviewService(db)
    with pytest.raises(ValidationException):
        service.submit_review_with_tip(
            student_id=test_booking.student_id,
            booking_id=test_booking.id,
            rating=5,
            tip_amount_cents=500,
        )


def test_submit_review_with_tip_missing_connected_account_raises(db, test_booking):
    _complete_booking(db, test_booking)
    payment_repo = PaymentRepository(db)
    payment_repo.create_customer_record(test_booking.student_id, "cus_review_tip_missing")
    db.commit()

    service = ReviewService(db)
    with pytest.raises(ValidationException):
        service.submit_review_with_tip(
            student_id=test_booking.student_id,
            booking_id=test_booking.id,
            rating=5,
            tip_amount_cents=500,
        )


def test_submit_review_with_tip_requires_action_sets_client_secret(
    db, test_booking, monkeypatch
):
    _complete_booking(db, test_booking)
    payment_repo = PaymentRepository(db)
    payment_repo.create_customer_record(test_booking.student_id, "cus_review_tip_action")
    payment_repo.save_payment_method(
        test_booking.student_id,
        "pm_default",
        "4242",
        "visa",
        is_default=True,
    )
    instructor_profile = _get_instructor_profile(db, test_booking.instructor_id)
    payment_repo.create_connected_account_record(instructor_profile.id, "acct_tip_action")
    db.commit()

    monkeypatch.setattr(settings, "stripe_secret_key", SecretStr("sk_test"))

    service = ReviewService(db)
    with patch(
        "app.services.review_service.StripeService.create_payment_intent",
        return_value=SimpleNamespace(
            stripe_payment_intent_id="pi_tip_action",
            status="requires_confirmation",
        ),
    ), patch(
        "app.services.review_service.StripeService.confirm_payment_intent",
        return_value=SimpleNamespace(
            id="pi_tip_action",
            status="requires_action",
        ),
    ), patch(
        "stripe.PaymentIntent.retrieve",
        return_value=SimpleNamespace(client_secret="secret_123"),
    ):
        result = service.submit_review_with_tip(
            student_id=test_booking.student_id,
            booking_id=test_booking.id,
            rating=5,
            review_text="Great",
            tip_amount_cents=500,
        )

    assert result["tip_status"] == "requires_action"
    assert result["tip_client_secret"] == "secret_123"


def test_submit_review_with_tip_confirms_success(db, test_booking):
    _complete_booking(db, test_booking)
    payment_repo = PaymentRepository(db)
    payment_repo.create_customer_record(test_booking.student_id, "cus_review_tip_success")
    payment_repo.save_payment_method(
        test_booking.student_id,
        "pm_default",
        "4242",
        "visa",
        is_default=True,
    )
    instructor_profile = _get_instructor_profile(db, test_booking.instructor_id)
    payment_repo.create_connected_account_record(instructor_profile.id, "acct_tip_ok")
    db.commit()

    service = ReviewService(db)
    with patch(
        "app.services.review_service.StripeService.create_payment_intent",
        return_value=SimpleNamespace(
            stripe_payment_intent_id="pi_tip_success",
            status="requires_confirmation",
        ),
    ), patch(
        "app.services.review_service.StripeService.confirm_payment_intent",
        return_value=SimpleNamespace(
            id="pi_tip_success",
            status="succeeded",
        ),
    ):
        result = service.submit_review_with_tip(
            student_id=test_booking.student_id,
            booking_id=test_booking.id,
            rating=5,
            review_text="Great",
            tip_amount_cents=500,
        )

    assert result["tip_status"] == "succeeded"
    assert result["tip_client_secret"] is None


def test_submit_review_with_tip_confirm_failure_sets_requires_payment_method(db, test_booking):
    _complete_booking(db, test_booking)
    payment_repo = PaymentRepository(db)
    payment_repo.create_customer_record(test_booking.student_id, "cus_review_tip_fail")
    payment_repo.save_payment_method(
        test_booking.student_id,
        "pm_default",
        "4242",
        "visa",
        is_default=True,
    )
    instructor_profile = _get_instructor_profile(db, test_booking.instructor_id)
    payment_repo.create_connected_account_record(instructor_profile.id, "acct_tip_fail")
    db.commit()

    service = ReviewService(db)
    with patch(
        "app.services.review_service.StripeService.create_payment_intent",
        return_value=SimpleNamespace(
            stripe_payment_intent_id="pi_tip_fail",
            status="requires_confirmation",
        ),
    ), patch(
        "app.services.review_service.StripeService.confirm_payment_intent",
        side_effect=Exception("confirm failed"),
    ):
        result = service.submit_review_with_tip(
            student_id=test_booking.student_id,
            booking_id=test_booking.id,
            rating=5,
            review_text="Great",
            tip_amount_cents=500,
        )

    assert result["tip_status"] == "requires_payment_method"
    assert result["tip_client_secret"] is None


def test_get_instructor_ratings_cache_hit_with_profile_id(db, test_booking):
    cache = DummyCache()
    service = ReviewService(db, cache=cache)
    profile = _get_instructor_profile(db, test_booking.instructor_id)
    cached_key = f"ratings:{service.CACHE_VERSION}:instructor:{profile.user_id}"
    cached_value = {
        "overall": {"rating": 4.8, "total_reviews": 12, "display_rating": "4.8★"},
        "by_service": [],
        "confidence_level": "established",
    }
    cache.data[cached_key] = cached_value

    result = service.get_instructor_ratings(profile.id)
    assert result == cached_value


def test_get_instructor_ratings_computes_and_caches(db, test_booking):
    cache = DummyCache()
    service = ReviewService(db, cache=cache)

    _complete_booking(db, test_booking)
    service.submit_review(
        student_id=test_booking.student_id,
        booking_id=test_booking.id,
        rating=5,
    )

    for offset in range(1, 3):
        booking = create_booking_pg_safe(
            db,
            student_id=test_booking.student_id,
            instructor_id=test_booking.instructor_id,
            instructor_service_id=test_booking.instructor_service_id,
            booking_date=test_booking.booking_date + timedelta(days=offset),
            start_time=test_booking.start_time,
            end_time=test_booking.end_time,
            service_name=test_booking.service_name,
            hourly_rate=test_booking.hourly_rate,
            total_price=test_booking.total_price,
            duration_minutes=test_booking.duration_minutes,
            status=BookingStatus.COMPLETED,
            offset_index=offset,
        )
        booking.completed_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.flush()
        service.submit_review(
            student_id=booking.student_id,
            booking_id=booking.id,
            rating=4,
        )

    ratings = service.get_instructor_ratings(test_booking.instructor_id)
    assert ratings["overall"]["total_reviews"] >= 3
    assert ratings["overall"]["display_rating"] is not None
    cache_key = f"ratings:{service.CACHE_VERSION}:instructor:{test_booking.instructor_id}"
    assert cache_key in cache.data


def test_get_rating_for_search_context_service_specific_and_overall(db, test_booking):
    cache = DummyCache()
    service = ReviewService(db, cache=cache)

    _complete_booking(db, test_booking)
    service.submit_review(
        student_id=test_booking.student_id,
        booking_id=test_booking.id,
        rating=5,
    )

    service_specific = service.get_rating_for_search_context(
        test_booking.instructor_id,
        test_booking.instructor_service_id,
    )
    overall = service.get_rating_for_search_context(test_booking.instructor_id)

    assert service_specific["is_service_specific"] is True
    assert overall["is_service_specific"] is False


def test_add_instructor_response_creates_and_notifies(db, test_booking):
    _complete_booking(db, test_booking)
    notifier = MagicMock()
    service = ReviewService(db, notification_service=notifier)
    review = service.submit_review(
        student_id=test_booking.student_id,
        booking_id=test_booking.id,
        rating=5,
        review_text="Great lesson",
    )

    response = service.add_instructor_response(
        review_id=review.id,
        instructor_id=test_booking.instructor_id,
        response_text="Thanks for the feedback!",
    )

    assert response.id is not None
    assert notifier.notify_user_best_effort.called


def test_add_instructor_response_without_notification_service(db, test_booking):
    _complete_booking(db, test_booking)
    service = ReviewService(db)
    review = service.submit_review(
        student_id=test_booking.student_id,
        booking_id=test_booking.id,
        rating=5,
        review_text="Great lesson",
    )

    response = service.add_instructor_response(
        review_id=review.id,
        instructor_id=test_booking.instructor_id,
        response_text="Thanks!",
    )

    assert response.id is not None


def test_add_instructor_response_notification_failure_is_non_blocking(db, test_booking):
    class FailingNotifier:
        def notify_user_best_effort(self, **kwargs):
            raise RuntimeError("notify failed")

    _complete_booking(db, test_booking)
    service = ReviewService(db, notification_service=FailingNotifier())
    review = service.submit_review(
        student_id=test_booking.student_id,
        booking_id=test_booking.id,
        rating=5,
        review_text="Great lesson",
    )

    response = service.add_instructor_response(
        review_id=review.id,
        instructor_id=test_booking.instructor_id,
        response_text="Thanks for the feedback!",
    )

    assert response.id is not None


def test_get_existing_reviews_for_bookings_filters_by_student(db, test_booking, test_password):
    _complete_booking(db, test_booking)
    service = ReviewService(db)
    service.submit_review(
        student_id=test_booking.student_id,
        booking_id=test_booking.id,
        rating=5,
    )

    other_student = _create_student(db, test_password)
    other_booking = create_booking_pg_safe(
        db,
        student_id=other_student.id,
        instructor_id=test_booking.instructor_id,
        instructor_service_id=test_booking.instructor_service_id,
        booking_date=test_booking.booking_date + timedelta(days=2),
        start_time=test_booking.start_time,
        end_time=test_booking.end_time,
        service_name=test_booking.service_name,
        hourly_rate=test_booking.hourly_rate,
        total_price=test_booking.total_price,
        duration_minutes=test_booking.duration_minutes,
        status=BookingStatus.COMPLETED,
        offset_index=5,
    )
    other_booking.completed_at = datetime.now(timezone.utc) - timedelta(hours=2)
    db.flush()
    service.submit_review(
        student_id=other_student.id,
        booking_id=other_booking.id,
        rating=4,
    )

    db.current_student_id = test_booking.student_id
    existing = service.get_existing_reviews_for_bookings([test_booking.id, other_booking.id])
    assert existing == [test_booking.id]


def test_get_rating_for_search_context_without_cache(db, test_booking):
    service = ReviewService(db)
    _complete_booking(db, test_booking)
    service.submit_review(
        student_id=test_booking.student_id,
        booking_id=test_booking.id,
        rating=5,
    )

    service_specific = service.get_rating_for_search_context(
        test_booking.instructor_id,
        test_booking.instructor_service_id,
    )
    overall = service.get_rating_for_search_context(test_booking.instructor_id)

    assert service_specific["is_service_specific"] is True
    assert overall["is_service_specific"] is False


def test_get_reviewer_display_name_variants(db, test_password):
    service = ReviewService(db)
    user = User(
        email=unique_email("review.display"),
        hashed_password=get_password_hash(test_password),
        first_name="Only",
        last_name="",
        zip_code="10001",
        is_active=True,
    )
    db.add(user)
    db.flush()

    assert service.get_reviewer_display_name("missing") is None
    assert service.get_reviewer_display_name(user.id) == "Only"


def test_review_service_helpers(db, test_booking):
    service = ReviewService(db)
    assert service._moderate_text("") == service._moderate_text(None)
    assert service._moderate_text("aa") != service._moderate_text("valid text")
    assert service._moderate_text("a" * 10) != service._moderate_text("valid text")
    assert service._bayesian(10, 2) > 0
    assert service._dirichlet_prior_mean() > 0
    assert service._confidence(1) == "new"
    assert service._confidence(10) == "establishing"
    assert service._confidence(50) == "established"
    assert service._confidence(150) == "trusted"
    assert "New" in (service._display(4.2, 4) or "")
    assert service._display(4.2, 5) and "New" not in service._display(4.2, 5)


def test_invalidate_instructor_caches_handles_delete_errors(db, test_booking):
    class BrokenCache(DummyCache):
        def delete(self, key: str) -> None:
            raise RuntimeError("cache delete failed")

    service = ReviewService(db, cache=BrokenCache())
    service._invalidate_instructor_caches(test_booking.instructor_id)
