from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from app.core.exceptions import RepositoryException
from app.models.review import ReviewStatus
from app.repositories.review_repository import (
    ReviewRepository,
    ReviewResponseRepository,
    ReviewTipRepository,
)


def test_review_aggregates_empty(db):
    repo = ReviewRepository(db)
    assert repo.get_instructor_aggregates("missing") == {
        "total_reviews": 0,
        "raw_average": 0.0,
        "rating_sum": 0,
    }
    assert repo.get_service_aggregates("missing", "missing") == {
        "review_count": 0,
        "raw_average": 0.0,
        "rating_sum": 0,
    }
    assert repo.get_service_breakdown("missing") == []


def test_review_crud_and_aggregates(db, test_booking):
    repo = ReviewRepository(db)

    assert repo.exists_for_booking(test_booking.id) is False
    repo.create_review(
        booking_id=test_booking.id,
        student_id=test_booking.student_id,
        instructor_id=test_booking.instructor_id,
        instructor_service_id=test_booking.instructor_service_id,
        rating=5,
        status=ReviewStatus.PUBLISHED.value,
        is_verified=True,
        booking_completed_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db.commit()

    assert repo.exists_for_booking(test_booking.id) is True
    assert repo.get_by_booking_id(test_booking.id) is not None

    aggregates = repo.get_instructor_aggregates(test_booking.instructor_id)
    assert aggregates["total_reviews"] == 1

    service = repo.get_service_aggregates(
        test_booking.instructor_id, test_booking.instructor_service_id
    )
    assert service["review_count"] == 1

    breakdown = repo.get_service_breakdown(test_booking.instructor_id)
    assert breakdown[0]["rating_sum"] == 5


def test_recent_reviews_filters(db, test_booking):
    repo = ReviewRepository(db)

    repo.create_review(
        booking_id=test_booking.id,
        student_id=test_booking.student_id,
        instructor_id=test_booking.instructor_id,
        instructor_service_id=test_booking.instructor_service_id,
        rating=4,
        status=ReviewStatus.PUBLISHED.value,
        is_verified=True,
        review_text="Great",
        booking_completed_at=datetime.now(timezone.utc),
    )
    db.commit()

    recent = repo.get_recent_reviews(test_booking.instructor_id, min_rating=4, with_text=True)
    assert len(recent) == 1

    count = repo.count_recent_reviews(test_booking.instructor_id, rating=4)
    assert count == 1

    by_service = repo.get_recent_reviews(
        test_booking.instructor_id,
        instructor_service_id=test_booking.instructor_service_id,
        rating=4,
    )
    assert len(by_service) == 1


def test_existing_and_verified_queries(db, test_booking):
    repo = ReviewRepository(db)

    repo.create_review(
        booking_id=test_booking.id,
        student_id=test_booking.student_id,
        instructor_id=test_booking.instructor_id,
        instructor_service_id=test_booking.instructor_service_id,
        rating=3,
        status=ReviewStatus.FLAGGED.value,
        is_verified=True,
        booking_completed_at=datetime.now(timezone.utc),
    )
    db.commit()

    existing = repo.get_existing_for_bookings([test_booking.id])
    assert existing == [test_booking.id]

    verified = repo.get_published_verified_for_instructor(test_booking.instructor_id)
    assert len(verified) == 1


def test_review_response_and_tip_repos(db, test_booking):
    review_repo = ReviewRepository(db)
    response_repo = ReviewResponseRepository(db)
    tip_repo = ReviewTipRepository(db)

    review = review_repo.create_review(
        booking_id=test_booking.id,
        student_id=test_booking.student_id,
        instructor_id=test_booking.instructor_id,
        instructor_service_id=test_booking.instructor_service_id,
        rating=5,
        status=ReviewStatus.PUBLISHED.value,
        booking_completed_at=datetime.now(timezone.utc),
    )
    db.commit()

    response_repo.create_response(
        review_id=review.id,
        instructor_id=test_booking.instructor_id,
        response_text="Thanks!",
    )
    db.commit()
    assert response_repo.exists_for_review(review.id) is True

    tip = tip_repo.create_tip(
        review_id=review.id,
        amount_cents=500,
        status="pending",
    )
    db.commit()

    updated = tip_repo.update_tip_status(tip.id, "completed")
    assert updated is not None

    by_review = tip_repo.get_by_review_id(review.id)
    assert by_review is not None

    by_booking = tip_repo.get_by_booking_id(test_booking.id)
    assert by_booking is not None

    updated = tip_repo.set_payment_intent_details(
        tip.id,
        stripe_payment_intent_id="pi_test",
        status="completed",
        processed_at=datetime.now(timezone.utc),
    )
    assert updated is not None

    assert tip_repo.update_tip_status("missing", "completed") is None
    assert (
        tip_repo.set_payment_intent_details(
            "missing", stripe_payment_intent_id=None, status=None
        )
        is None
    )


def test_review_repository_error_paths():
    db = Mock()
    db.add.side_effect = RuntimeError("boom")
    db.flush.side_effect = RuntimeError("boom")
    db.query.side_effect = RuntimeError("boom")
    repo = ReviewRepository(db)

    with pytest.raises(RepositoryException):
        repo.create_review(booking_id="booking")

    with pytest.raises(RepositoryException):
        repo.exists_for_booking("booking")

    with pytest.raises(RepositoryException):
        repo.get_by_booking_id("booking")

    with pytest.raises(RepositoryException):
        repo.get_instructor_aggregates("instructor")

    with pytest.raises(RepositoryException):
        repo.get_service_aggregates("instructor", "service")

    with pytest.raises(RepositoryException):
        repo.get_service_breakdown("instructor")

    with pytest.raises(RepositoryException):
        repo.get_recent_reviews("instructor")

    with pytest.raises(RepositoryException):
        repo.count_recent_reviews("instructor")

    with pytest.raises(RepositoryException):
        repo.get_existing_for_bookings(["booking"])

    with pytest.raises(RepositoryException):
        repo.get_published_verified_for_instructor("instructor")

    response_repo = ReviewResponseRepository(db)
    with pytest.raises(RepositoryException):
        response_repo.create_response(review_id="review")

    with pytest.raises(RepositoryException):
        response_repo.exists_for_review("review")

    tip_repo = ReviewTipRepository(db)
    with pytest.raises(RepositoryException):
        tip_repo.create_tip(review_id="review", amount_cents=100, status="pending")

    with pytest.raises(RepositoryException):
        tip_repo.update_tip_status("tip", "completed")

    with pytest.raises(RepositoryException):
        tip_repo.get_by_review_id("review")

    with pytest.raises(RepositoryException):
        tip_repo.get_by_booking_id("booking")

    with pytest.raises(RepositoryException):
        tip_repo.set_payment_intent_details("tip", stripe_payment_intent_id="pi_test")
