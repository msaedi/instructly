from datetime import datetime, timedelta, timezone

from app.models.booking import BookingStatus
from app.repositories.review_repository import ReviewRepository


def test_repository_aggregations(db, test_booking):
    # Prepare: completed and review submitted
    test_booking.status = BookingStatus.COMPLETED
    test_booking.completed_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.flush()

    repo = ReviewRepository(db)
    # Create a couple of reviews across same service
    from app.models.review import Review, ReviewStatus

    r1 = Review(
        booking_id=test_booking.id,
        student_id=test_booking.student_id,
        instructor_id=test_booking.instructor_id,
        instructor_service_id=test_booking.instructor_service_id,
        rating=5,
        status=ReviewStatus.PUBLISHED,
        is_verified=True,
        booking_completed_at=test_booking.completed_at,
    )
    db.add(r1)
    db.flush()

    overall = repo.get_instructor_aggregates(test_booking.instructor_id)
    assert overall["total_reviews"] == 1
    assert overall["rating_sum"] == 5

    service = repo.get_service_aggregates(test_booking.instructor_id, test_booking.instructor_service_id)
    assert service["review_count"] == 1
    assert service["rating_sum"] == 5
