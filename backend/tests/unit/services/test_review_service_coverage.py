"""
Unit tests for ReviewService targeting coverage improvements.

Coverage focus:
- submit_review validation paths (lines 122-217)
- submit_review_with_tip tip processing (lines 320-422)
- get_instructor_ratings cache paths (lines 435-470)
- get_rating_for_search_context (lines 548-580)
- add_instructor_response validation (lines 587-633)
- get_existing_reviews_for_bookings edge cases (lines 525-542)

Strategy: Mock external dependencies (Stripe, notifications), test business logic
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException, ValidationException
from app.models.booking import BookingStatus
from app.services.review_service import ReviewService


@pytest.fixture
def mock_db():
    """Create mock database session."""
    db = MagicMock(spec=Session)
    return db


@pytest.fixture
def mock_cache():
    """Create mock cache service."""
    cache = MagicMock()
    cache.get.return_value = None  # Cache miss by default
    return cache


@pytest.fixture
def mock_notification_service():
    """Create mock notification service."""
    return MagicMock()


@pytest.fixture
def review_service(mock_db, mock_cache, mock_notification_service):
    """Create ReviewService with mocked dependencies."""
    with patch.object(ReviewService, "__init__", lambda self, db, cache=None, config=None, notification_service=None: None):
        service = ReviewService.__new__(ReviewService)
        service.db = mock_db
        service.cache = mock_cache
        service.notification_service = mock_notification_service
        service.logger = MagicMock()
        service.repository = MagicMock()
        service.response_repository = MagicMock()
        service.tip_repository = MagicMock()
        service.booking_repository = MagicMock()
        service.instructor_profile_repository = MagicMock()
        service.config = MagicMock()
        service.config.min_reviews_to_display = 3
        service.config.prior_mean = 4.0
        service.config.shrinkage_weight = 5
        service.REVIEW_WINDOW_DAYS = 30
        service.CACHE_VERSION = "v2"
        return service


class TestSubmitReviewValidation:
    """Tests for submit_review validation paths."""

    def test_submit_review_invalid_rating_none(self, review_service):
        """Test submit_review rejects None rating."""
        with pytest.raises(ValidationException) as exc_info:
            review_service.submit_review(
                student_id="student-1",
                booking_id="booking-1",
                rating=None,
            )
        assert "between 1 and 5" in str(exc_info.value)

    def test_submit_review_invalid_rating_too_low(self, review_service):
        """Test submit_review rejects rating < 1."""
        with pytest.raises(ValidationException) as exc_info:
            review_service.submit_review(
                student_id="student-1",
                booking_id="booking-1",
                rating=0,
            )
        assert "between 1 and 5" in str(exc_info.value)

    def test_submit_review_invalid_rating_too_high(self, review_service):
        """Test submit_review rejects rating > 5."""
        with pytest.raises(ValidationException) as exc_info:
            review_service.submit_review(
                student_id="student-1",
                booking_id="booking-1",
                rating=6,
            )
        assert "between 1 and 5" in str(exc_info.value)

    def test_submit_review_text_too_long(self, review_service):
        """Test submit_review rejects review text > 500 chars."""
        review_service.booking_repository.get_by_id.return_value = MagicMock()

        with pytest.raises(ValidationException) as exc_info:
            review_service.submit_review(
                student_id="student-1",
                booking_id="booking-1",
                rating=5,
                review_text="x" * 501,
            )
        assert "500 characters" in str(exc_info.value)

    def test_submit_review_booking_not_found(self, review_service):
        """Test submit_review raises NotFoundException for missing booking."""
        review_service.booking_repository.get_by_id.return_value = None

        with pytest.raises(NotFoundException) as exc_info:
            review_service.submit_review(
                student_id="student-1",
                booking_id="nonexistent",
                rating=5,
            )
        assert "Booking not found" in str(exc_info.value)

    def test_submit_review_wrong_student(self, review_service):
        """Test submit_review rejects review from wrong student."""
        booking = MagicMock()
        booking.student_id = "other-student"
        review_service.booking_repository.get_by_id.return_value = booking

        with pytest.raises(ValidationException) as exc_info:
            review_service.submit_review(
                student_id="student-1",
                booking_id="booking-1",
                rating=5,
            )
        assert "your own booking" in str(exc_info.value)

    def test_submit_review_no_show_booking(self, review_service):
        """Test submit_review rejects no-show booking."""
        booking = MagicMock()
        booking.student_id = "student-1"
        booking.status = BookingStatus.NO_SHOW
        review_service.booking_repository.get_by_id.return_value = booking

        with pytest.raises(ValidationException) as exc_info:
            review_service.submit_review(
                student_id="student-1",
                booking_id="booking-1",
                rating=5,
            )
        assert "no-show" in str(exc_info.value).lower()

    def test_submit_review_pending_booking(self, review_service):
        """Test submit_review rejects pending booking."""
        booking = MagicMock()
        booking.student_id = "student-1"
        booking.status = BookingStatus.PENDING
        review_service.booking_repository.get_by_id.return_value = booking

        with pytest.raises(ValidationException) as exc_info:
            review_service.submit_review(
                student_id="student-1",
                booking_id="booking-1",
                rating=5,
            )
        assert "completed" in str(exc_info.value).lower()


class TestSubmitReviewExpiredWindow:
    """Tests for review window expiration."""

    def test_submit_review_expired_window(self, review_service):
        """Test submit_review rejects reviews after 30-day window."""
        booking = MagicMock()
        booking.student_id = "student-1"
        booking.status = BookingStatus.COMPLETED
        # Set completed_at to 31 days ago
        booking.completed_at = datetime.now(timezone.utc) - timedelta(days=31)
        review_service.booking_repository.get_by_id.return_value = booking

        with pytest.raises(ValidationException) as exc_info:
            review_service.submit_review(
                student_id="student-1",
                booking_id="booking-1",
                rating=5,
            )
        assert "expired" in str(exc_info.value).lower()


class TestSubmitReviewDuplicate:
    """Tests for duplicate review prevention."""

    def test_submit_review_already_exists(self, review_service):
        """Test submit_review rejects duplicate review."""
        booking = MagicMock()
        booking.student_id = "student-1"
        booking.status = BookingStatus.COMPLETED
        booking.completed_at = datetime.now(timezone.utc) - timedelta(days=1)
        review_service.booking_repository.get_by_id.return_value = booking
        review_service.repository.exists_for_booking.return_value = True

        with pytest.raises(ValidationException) as exc_info:
            review_service.submit_review(
                student_id="student-1",
                booking_id="booking-1",
                rating=5,
            )
        assert "already submitted" in str(exc_info.value).lower()


class TestGetInstructorRatingsCachePaths:
    """Tests for get_instructor_ratings cache handling."""

    def test_get_instructor_ratings_cache_hit(self, review_service):
        """Test get_instructor_ratings returns cached result."""
        cached_result = {
            "overall": {"rating": 4.5, "total_reviews": 10, "display_rating": "4.5"},
            "by_service": [],
            "confidence_level": "high",
        }
        review_service.cache.get.return_value = cached_result
        review_service.instructor_profile_repository.get_by_id.return_value = None

        result = review_service.get_instructor_ratings("instructor-1")

        assert result == cached_result
        review_service.cache.get.assert_called()

    def test_get_instructor_ratings_cache_miss(self, review_service):
        """Test get_instructor_ratings computes and caches on miss."""
        review_service.cache.get.return_value = None
        review_service.instructor_profile_repository.get_by_id.return_value = None
        review_service.repository.get_histogram.return_value = [0, 0, 0, 5, 15]
        review_service.repository.get_service_breakdown.return_value = []

        result = review_service.get_instructor_ratings("instructor-1")

        assert "overall" in result
        review_service.cache.set.assert_called()


class TestGetRatingForSearchContext:
    """Tests for get_rating_for_search_context."""

    def test_get_rating_service_specific(self, review_service):
        """Test get_rating_for_search_context with service filter."""
        review_service.cache.get.return_value = None
        review_service.instructor_profile_repository.get_by_id.return_value = None
        review_service.repository.get_histogram_for_service.return_value = [0, 0, 1, 3, 6]

        result = review_service.get_rating_for_search_context(
            "instructor-1", instructor_service_id="service-1"
        )

        assert result["is_service_specific"] == True
        assert "primary_rating" in result
        assert "review_count" in result

    def test_get_rating_overall(self, review_service):
        """Test get_rating_for_search_context without service filter."""
        review_service.cache.get.return_value = None
        review_service.instructor_profile_repository.get_by_id.return_value = None
        review_service.repository.get_histogram.return_value = [0, 1, 2, 5, 12]

        result = review_service.get_rating_for_search_context("instructor-1")

        assert result["is_service_specific"] == False

    def test_get_rating_cache_hit(self, review_service):
        """Test get_rating_for_search_context cache hit."""
        cached = {"primary_rating": 4.3, "review_count": 15, "is_service_specific": False}
        review_service.cache.get.return_value = cached
        review_service.instructor_profile_repository.get_by_id.return_value = None

        result = review_service.get_rating_for_search_context("instructor-1")

        assert result == cached


class TestAddInstructorResponse:
    """Tests for add_instructor_response validation."""

    def test_add_response_empty_text(self, review_service):
        """Test add_instructor_response rejects empty text."""
        with pytest.raises(ValidationException) as exc_info:
            review_service.add_instructor_response(
                review_id="review-1",
                instructor_id="instructor-1",
                response_text="",
            )
        assert "empty" in str(exc_info.value).lower()

    def test_add_response_whitespace_only(self, review_service):
        """Test add_instructor_response rejects whitespace-only text."""
        with pytest.raises(ValidationException) as exc_info:
            review_service.add_instructor_response(
                review_id="review-1",
                instructor_id="instructor-1",
                response_text="   ",
            )
        assert "empty" in str(exc_info.value).lower()

    def test_add_response_text_too_long(self, review_service):
        """Test add_instructor_response rejects text > 500 chars."""
        with pytest.raises(ValidationException) as exc_info:
            review_service.add_instructor_response(
                review_id="review-1",
                instructor_id="instructor-1",
                response_text="x" * 501,
            )
        assert "500" in str(exc_info.value)

    def test_add_response_review_not_found(self, review_service):
        """Test add_instructor_response raises NotFoundException."""
        review_service.repository.get_by_id.return_value = None

        with pytest.raises(NotFoundException) as exc_info:
            review_service.add_instructor_response(
                review_id="nonexistent",
                instructor_id="instructor-1",
                response_text="Thank you!",
            )
        assert "not found" in str(exc_info.value).lower()

    def test_add_response_wrong_instructor(self, review_service):
        """Test add_instructor_response rejects wrong instructor."""
        review = MagicMock()
        review.instructor_id = "other-instructor"
        review_service.repository.get_by_id.return_value = review

        with pytest.raises(ValidationException) as exc_info:
            review_service.add_instructor_response(
                review_id="review-1",
                instructor_id="instructor-1",
                response_text="Thank you!",
            )
        assert "your own" in str(exc_info.value).lower()

    def test_add_response_already_exists(self, review_service):
        """Test add_instructor_response rejects duplicate response."""
        review = MagicMock()
        review.instructor_id = "instructor-1"
        review_service.repository.get_by_id.return_value = review
        review_service.response_repository.exists_for_review.return_value = True

        with pytest.raises(ValidationException) as exc_info:
            review_service.add_instructor_response(
                review_id="review-1",
                instructor_id="instructor-1",
                response_text="Thank you!",
            )
        assert "already submitted" in str(exc_info.value).lower()


class TestGetExistingReviewsForBookings:
    """Tests for get_existing_reviews_for_bookings edge cases."""

    def test_get_existing_reviews_empty_list(self, review_service):
        """Test with empty booking_ids returns empty list."""
        result = review_service.get_existing_reviews_for_bookings([])
        assert result == []

    def test_get_existing_reviews_with_student_context(self, review_service):
        """Test with student context filters by ownership."""
        review_service.db.current_student_id = "student-1"
        review_service.booking_repository.filter_owned_booking_ids.return_value = ["booking-1"]
        review_service.repository.get_existing_for_bookings.return_value = ["booking-1"]

        result = review_service.get_existing_reviews_for_bookings(["booking-1", "booking-2"])

        review_service.booking_repository.filter_owned_booking_ids.assert_called_with(
            ["booking-1", "booking-2"], "student-1"
        )
        assert result == ["booking-1"]

    def test_get_existing_reviews_no_owned_bookings(self, review_service):
        """Test returns empty when no owned bookings."""
        review_service.db.current_student_id = "student-1"
        review_service.booking_repository.filter_owned_booking_ids.return_value = []

        result = review_service.get_existing_reviews_for_bookings(["booking-1"])

        assert result == []

    def test_get_existing_reviews_exception_returns_empty(self, review_service):
        """Test returns empty list on exception."""
        review_service.db.current_student_id = None
        review_service.repository.get_existing_for_bookings.side_effect = Exception("DB error")

        result = review_service.get_existing_reviews_for_bookings(["booking-1"])

        assert result == []


class TestResolveInstructorUserId:
    """Tests for _resolve_instructor_user_id helper."""

    def test_resolve_with_profile_id(self, review_service):
        """Test resolving profile ID to user ID."""
        profile = MagicMock()
        profile.user_id = "user-123"
        review_service.instructor_profile_repository.get_by_id.return_value = profile

        result = review_service._resolve_instructor_user_id("profile-456")

        assert result == "user-123"

    def test_resolve_no_profile(self, review_service):
        """Test fallback when no profile found."""
        review_service.instructor_profile_repository.get_by_id.return_value = None

        result = review_service._resolve_instructor_user_id("user-789")

        assert result == "user-789"

    def test_resolve_exception_fallback(self, review_service):
        """Test fallback on exception."""
        review_service.instructor_profile_repository.get_by_id.side_effect = Exception("Error")

        result = review_service._resolve_instructor_user_id("some-id")

        assert result == "some-id"


class TestGetReviewForBooking:
    """Tests for get_review_for_booking."""

    def test_get_review_found(self, review_service):
        """Test get_review_for_booking returns review."""
        review = MagicMock()
        review_service.repository.get_by_booking_id.return_value = review

        result = review_service.get_review_for_booking("booking-1")

        assert result == review

    def test_get_review_not_found(self, review_service):
        """Test get_review_for_booking returns None."""
        review_service.repository.get_by_booking_id.return_value = None

        result = review_service.get_review_for_booking("booking-1")

        assert result is None


class TestGetRecentReviews:
    """Tests for get_recent_reviews."""

    def test_get_recent_reviews_basic(self, review_service):
        """Test get_recent_reviews basic call."""
        reviews = [MagicMock(), MagicMock()]
        review_service.instructor_profile_repository.get_by_id.return_value = None
        review_service.repository.get_recent_reviews.return_value = reviews

        result = review_service.get_recent_reviews(
            instructor_id="instructor-1",
            limit=10,
            page=1,
        )

        assert result == reviews

    def test_get_recent_reviews_with_filters(self, review_service):
        """Test get_recent_reviews with filters."""
        reviews = [MagicMock()]
        review_service.instructor_profile_repository.get_by_id.return_value = None
        review_service.repository.get_recent_reviews.return_value = reviews

        review_service.get_recent_reviews(
            instructor_id="instructor-1",
            instructor_service_id="service-1",
            limit=5,
            page=2,
            min_rating=4,
            with_text=True,
        )

        review_service.repository.get_recent_reviews.assert_called_once()


class TestCountRecentReviews:
    """Tests for count_recent_reviews."""

    def test_count_recent_reviews(self, review_service):
        """Test count_recent_reviews."""
        review_service.instructor_profile_repository.get_by_id.return_value = None
        review_service.repository.count_recent_reviews.return_value = 42

        result = review_service.count_recent_reviews(instructor_id="instructor-1")

        assert result == 42
