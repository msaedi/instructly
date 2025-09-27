from datetime import datetime, timedelta, timezone

import pytest

from app.models.booking import BookingStatus
from app.models.review import ReviewStatus
from app.services.review_service import ReviewService


def _complete_booking(db, booking):
    booking.status = BookingStatus.COMPLETED
    booking.completed_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.flush()


def test_submit_review_success(db, test_booking):
    # Mark as completed and within window
    _complete_booking(db, test_booking)
    svc = ReviewService(db, cache=None)

    review = svc.submit_review(
        student_id=test_booking.student_id,
        booking_id=test_booking.id,
        rating=5,
        review_text="Great lesson!",
    )

    assert review is not None
    assert review.rating == 5
    assert review.status in {ReviewStatus.PUBLISHED, ReviewStatus.FLAGGED}


def test_submit_review_duplicate_prevented(db, test_booking):
    _complete_booking(db, test_booking)
    svc = ReviewService(db)
    svc.submit_review(
        student_id=test_booking.student_id,
        booking_id=test_booking.id,
        rating=4,
    )

    with pytest.raises(Exception):
        svc.submit_review(
            student_id=test_booking.student_id,
            booking_id=test_booking.id,
            rating=3,
        )


def test_submit_review_window_expired(db, test_booking):
    # Completed 40 days ago
    test_booking.status = BookingStatus.COMPLETED
    test_booking.completed_at = datetime.now(timezone.utc) - timedelta(days=40)
    db.flush()

    svc = ReviewService(db)
    with pytest.raises(Exception):
        svc.submit_review(
            student_id=test_booking.student_id,
            booking_id=test_booking.id,
            rating=5,
        )


def test_get_instructor_ratings_bayesian(db, test_booking):
    _complete_booking(db, test_booking)
    svc = ReviewService(db, cache=None)

    # Create 3 reviews to pass threshold
    for rating in [5, 4, 5]:
        # Make a new booking per review
        from app.models.booking import Booking

        b = Booking(
            student_id=test_booking.student_id,
            instructor_id=test_booking.instructor_id,
            instructor_service_id=test_booking.instructor_service_id,
            booking_date=test_booking.booking_date,
            start_time=test_booking.start_time,
            end_time=test_booking.end_time,
            service_name=test_booking.service_name,
            hourly_rate=test_booking.hourly_rate,
            total_price=test_booking.total_price,
            duration_minutes=test_booking.duration_minutes,
            status=BookingStatus.COMPLETED,
            completed_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        db.add(b)
        db.flush()
        svc.submit_review(student_id=b.student_id, booking_id=b.id, rating=rating)

    ratings = svc.get_instructor_ratings(test_booking.instructor_id)
    assert ratings["overall"]["rating"] > 0
    assert ratings["overall"]["total_reviews"] >= 3
    assert ratings["overall"]["display_rating"] is not None
