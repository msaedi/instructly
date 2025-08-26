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
    res = client.post("/api/reviews/submit", json=payload, headers=auth_headers)
    assert res.status_code in (200, 201)
    data = res.json()
    assert data["rating"] == 5


def test_get_instructor_ratings_route(client, db, test_booking, auth_headers):
    # Create a prior review quickly via route
    test_booking.status = "COMPLETED"
    test_booking.completed_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.flush()
    client.post(
        "/api/reviews/submit",
        json={"booking_id": test_booking.id, "rating": 4},
        headers=auth_headers,
    )

    res = client.get(f"/api/reviews/instructor/{test_booking.instructor_id}/ratings")
    assert res.status_code == 200
    data = res.json()
    assert "overall" in data


def test_recent_reviews_route(client, db, test_booking, auth_headers):
    test_booking.status = "COMPLETED"
    test_booking.completed_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.flush()
    client.post(
        "/api/reviews/submit",
        json={"booking_id": test_booking.id, "rating": 5},
        headers=auth_headers,
    )
    res = client.get(f"/api/reviews/instructor/{test_booking.instructor_id}/recent")
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

    submit = client.post(
        "/api/reviews/submit",
        json={"booking_id": test_booking.id, "rating": 4, "review_text": "solid"},
        headers=auth_headers,
    )
    assert submit.status_code in (200, 201)
    review_id = submit.json()["id"]

    # Instructor (owner) responds
    res = client.post(f"/api/reviews/reviews/{review_id}/respond?response_text=thanks", headers=auth_headers_instructor)
    assert res.status_code == 200
    body = res.json()
    assert body["review_id"] == review_id
    assert body["response_text"] == "thanks"

    # Another instructor cannot respond
    res2 = client.post(
        f"/api/reviews/reviews/{review_id}/respond?response_text=notallowed", headers=auth_headers_instructor_2
    )
    assert res2.status_code in (400, 403)
