"""
Reviews routes tests - Phase 12: Migrated to /api/v1/reviews
"""
from datetime import datetime, timedelta, timezone


def test_submit_review_route(client, db, test_booking, auth_headers):
    # Mark booking completed
    test_booking.status = "COMPLETED"
    test_booking.completed_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.flush()

    payload = {
        "booking_id": test_booking.id,
        "rating": 5,
        "review_text": "Great!",
    }
    # Phase 12: Reviews migrated to /api/v1/reviews
    res = client.post("/api/v1/reviews", json=payload, headers=auth_headers)
    assert res.status_code in (200, 201)
    data = res.json()
    assert data["rating"] == 5


def test_get_instructor_ratings_route(client, db, test_booking, auth_headers):
    # Create a prior review quickly via route
    test_booking.status = "COMPLETED"
    test_booking.completed_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.flush()
    # Phase 12: Reviews migrated to /api/v1/reviews
    client.post(
        "/api/v1/reviews",
        json={"booking_id": test_booking.id, "rating": 4},
        headers=auth_headers,
    )

    res = client.get(f"/api/v1/reviews/instructor/{test_booking.instructor_id}/ratings")
    assert res.status_code == 200
    data = res.json()
    assert "overall" in data


def test_get_instructor_ratings_accepts_instructor_profile_id(client, db, test_booking, auth_headers):
    # Create a review for the instructor (reviews store instructor as users.id)
    test_booking.status = "COMPLETED"
    test_booking.completed_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.flush()
    client.post(
        "/api/v1/reviews",
        json={"booking_id": test_booking.id, "rating": 5},
        headers=auth_headers,
    )

    # But public pages commonly use instructor_profiles.id; ensure the endpoint works with that too.
    from app.models.instructor import InstructorProfile

    profile = (
        db.query(InstructorProfile)
        .filter(InstructorProfile.user_id == test_booking.instructor_id)
        .first()
    )
    assert profile is not None

    res = client.get(f"/api/v1/reviews/instructor/{profile.id}/ratings")
    assert res.status_code == 200
    data = res.json()
    assert data["overall"]["total_reviews"] >= 1


def test_recent_reviews_route(client, db, test_booking, auth_headers):
    test_booking.status = "COMPLETED"
    test_booking.completed_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.flush()
    # Phase 12: Reviews migrated to /api/v1/reviews
    client.post(
        "/api/v1/reviews",
        json={"booking_id": test_booking.id, "rating": 5},
        headers=auth_headers,
    )
    res = client.get(f"/api/v1/reviews/instructor/{test_booking.instructor_id}/recent")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data.get("reviews"), list)


def test_respond_to_review_route(
    client, db, test_booking, auth_headers_instructor, auth_headers_instructor_2, auth_headers
):
    # Complete booking and submit a review as student
    test_booking.status = "COMPLETED"
    test_booking.completed_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.flush()

    # Phase 12: Reviews migrated to /api/v1/reviews
    submit = client.post(
        "/api/v1/reviews",
        json={"booking_id": test_booking.id, "rating": 4, "review_text": "solid"},
        headers=auth_headers,
    )
    assert submit.status_code in (200, 201)
    review_id = submit.json()["id"]

    # Instructor (owner) responds
    # Phase 13: v1 endpoint expects response_text in body (embed=True), not query params
    res = client.post(
        f"/api/v1/reviews/{review_id}/respond",
        json={"response_text": "thanks"},
        headers=auth_headers_instructor,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["review_id"] == review_id
    assert body["response_text"] == "thanks"

    # Another instructor cannot respond
    res2 = client.post(
        f"/api/v1/reviews/{review_id}/respond",
        json={"response_text": "notallowed"},
        headers=auth_headers_instructor_2,
    )
    assert res2.status_code in (400, 403)


# ========== NO_SHOW Blocking Tests (Part 10) ==========


def test_cannot_review_no_show_booking(client, db, test_booking, auth_headers):
    """Students cannot review bookings marked as no-show."""
    # Mark booking as NO_SHOW
    test_booking.status = "NO_SHOW"
    db.flush()

    payload = {
        "booking_id": test_booking.id,
        "rating": 5,
        "review_text": "Great lesson!",
    }
    res = client.post("/api/v1/reviews", json=payload, headers=auth_headers)
    assert res.status_code == 400
    data = res.json()
    assert "no-show" in data["detail"].lower()


def test_cannot_tip_no_show_booking(client, db, test_booking, auth_headers):
    """Students cannot tip on bookings marked as no-show (tips require review)."""
    # Mark booking as NO_SHOW
    test_booking.status = "NO_SHOW"
    db.flush()

    # Tips are submitted with reviews via tip_amount_cents field
    payload = {
        "booking_id": test_booking.id,
        "rating": 5,
        "review_text": "Amazing!",
        "tip_amount_cents": 2000,  # $20 tip
    }
    res = client.post("/api/v1/reviews", json=payload, headers=auth_headers)
    assert res.status_code == 400
    data = res.json()
    assert "no-show" in data["detail"].lower()


def test_can_review_completed_booking(client, db, test_booking, auth_headers):
    """Students CAN review completed bookings (regression test)."""
    test_booking.status = "COMPLETED"
    test_booking.completed_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.flush()

    payload = {
        "booking_id": test_booking.id,
        "rating": 4,
        "review_text": "Good lesson.",
    }
    res = client.post("/api/v1/reviews", json=payload, headers=auth_headers)
    assert res.status_code in (200, 201)
    data = res.json()
    assert data["rating"] == 4
