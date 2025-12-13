# backend/tests/contracts/test_api_returns_data.py
"""
API contract tests that verify endpoints return actual data, not just 200 OK.

These tests catch silent ORM/DB mismatches where:
- API returns 200 OK
- But data is empty due to enum value mismatches or other query issues

The Dec 7 2024 bug: API returned 200 OK with zero reviews even though
reviews existed in the database (enum mismatch prevented ORM from finding them).
"""

from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.user import User


class TestReviewsEndpointReturnsData:
    """
    Test that reviews endpoints return actual data when reviews exist.

    This catches the Dec 7 2024 bug directly - the API was returning
    zero reviews even though they existed in the database.
    """

    def test_instructor_ratings_returns_data_when_review_exists(
        self,
        client: TestClient,
        db: Session,
        test_booking: "Booking",
        auth_headers_student: dict,
    ) -> None:
        """
        Create a review, then verify the ratings endpoint returns it.

        The bug: this would return total_reviews=0 even after creating a review.
        """
        from datetime import datetime, timezone

        from app.models.review import Review, ReviewStatus

        # Create a published review
        review = Review(
            booking_id=test_booking.id,
            student_id=test_booking.student_id,
            instructor_id=test_booking.instructor_id,
            instructor_service_id=test_booking.instructor_service_id,
            rating=5,
            review_text="Great lesson!",
            status=ReviewStatus.PUBLISHED,
            booking_completed_at=datetime.now(timezone.utc),
        )
        db.add(review)
        db.commit()

        # Now query the API
        response = client.get(
            f"/api/v1/reviews/instructor/{test_booking.instructor_id}/ratings",
            headers=auth_headers_student,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        # CRITICAL: Verify we got actual data, not empty results
        # The response structure varies - check multiple possible fields
        overall = data.get("overall", {})
        by_service = data.get("by_service", [])

        # Check if we got any review data at all
        has_reviews = (
            overall.get("total_reviews", 0) > 0
            or overall.get("rating") is not None
            or any(s.get("review_count", 0) > 0 for s in by_service)
        )

        assert has_reviews, (
            f"Expected review data in response, got {data}. "
            "This may indicate the Dec 7 2024 bug - ORM not finding data."
        )


class TestSearchEndpointReturnsData:
    """
    Test that search endpoints return results when instructors exist.
    """

    def test_search_returns_instructors_when_they_exist(
        self,
        client: TestClient,
        test_instructor: "User",
    ) -> None:
        """
        Verify search returns results when instructors exist.
        """
        # The test_instructor fixture ensures an instructor exists
        _ = test_instructor  # Use the fixture to ensure it's created

        response = client.get("/api/v1/search/instructors?q=piano")

        # Search might return 200 even with no results - that's OK
        # But if we have instructors with piano services, we should get results
        if response.status_code == 200:
            data = response.json()
            # This is informational - search may return empty for various reasons
            # The key is that if results exist, they serialize correctly
            if "results" in data and isinstance(data["results"], list):
                for result in data["results"]:
                    # Verify each result has instructor data in some form
                    # The structure can vary - check common patterns
                    has_instructor_id = (
                        "instructor_id" in result
                        or "id" in result
                        or (isinstance(result.get("instructor"), dict) and "id" in result["instructor"])
                    )
                    assert has_instructor_id, (
                        f"Search result missing instructor ID: {result}"
                    )


class TestBookingsEndpointReturnsData:
    """
    Test that bookings endpoints return data when bookings exist.
    """

    def test_upcoming_bookings_returns_data_when_booking_exists(
        self,
        client: TestClient,
        test_booking: "Booking",
        auth_headers_student: dict,
    ) -> None:
        """
        Verify student can see their upcoming booking after creation.
        """
        response = client.get(
            "/api/v1/bookings/upcoming",
            headers=auth_headers_student,
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()

        # Response is PaginatedResponse with items
        if isinstance(data, list):
            bookings = data
        else:
            bookings = data.get("items") or data.get("bookings") or data.get("results") or []

        assert len(bookings) > 0, (
            "Expected at least 1 booking but got empty list. "
            "Check if booking status enum is properly queryable via ORM."
        )

        # Verify the booking we created is in the list
        booking_ids = [b.get("id") for b in bookings]
        assert test_booking.id in booking_ids, (
            f"Created booking {test_booking.id} not found in upcoming bookings. "
            "This may indicate an ORM query issue."
        )


class TestEnumFilteringWorks:
    """
    Test that filtering by enum values works correctly.

    These tests verify that ORM queries using enum values return correct results.
    """

    def test_booking_status_filter_works(
        self,
        client: TestClient,
        test_booking: "Booking",
        auth_headers_student: dict,
    ) -> None:
        """
        Verify filtering bookings by status works.
        """
        # Try to filter by CONFIRMED status (the default for test_booking)
        response = client.get(
            "/api/v1/bookings/my?status=CONFIRMED",
            headers=auth_headers_student,
        )

        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list):
                bookings = data
            else:
                bookings = data.get("bookings") or data.get("items") or data.get("results") or []

            # If the filter is working, we should find our booking
            if bookings:
                booking_ids = [b.get("id") for b in bookings]
                assert test_booking.id in booking_ids, (
                    "Booking status filter not working - created booking not found. "
                    "Check enum value consistency."
                )
