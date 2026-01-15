# backend/tests/routes/test_reviews_routes_coverage.py
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.core.exceptions import RepositoryException, ValidationException
from app.routes.v1 import reviews as reviews_routes
from app.schemas.review import RatingsBatchRequest, ReviewSubmitRequest


def test_display_name_none_and_blank():
    assert reviews_routes._display_name(None) is None
    user = SimpleNamespace(first_name=" ", last_name="Smith")
    assert reviews_routes._display_name(user) is None


def test_handle_domain_exception_without_helper():
    class _Dummy(Exception):
        pass

    with pytest.raises(reviews_routes.HTTPException):
        reviews_routes.handle_domain_exception(_Dummy("boom"))


def test_get_existing_reviews_empty_returns_empty(monkeypatch):
    class _BadDB:
        def __setattr__(self, *_args, **_kwargs):
            raise RuntimeError("no")

    class _Service:
        def __init__(self):
            self.db = _BadDB()

        def get_existing_reviews_for_bookings(self, *_args, **_kwargs):
            return []

    monkeypatch.setattr(
        reviews_routes.BookingRepository,
        "filter_owned_booking_ids",
        lambda *_args, **_kwargs: [],
    )
    current_user = SimpleNamespace(id="student-1")
    response = reviews_routes.get_existing_reviews_for_bookings(
        booking_ids=["b1"],
        current_user=current_user,
        service=_Service(),
    )
    assert response.root == []


def test_get_existing_reviews_returns_ids(monkeypatch):
    class _Service:
        def __init__(self):
            self.db = SimpleNamespace()

        def get_existing_reviews_for_bookings(self, booking_ids):
            return booking_ids

    monkeypatch.setattr(
        reviews_routes.BookingRepository,
        "filter_owned_booking_ids",
        lambda *_args, **_kwargs: ["b1", "b2"],
    )
    current_user = SimpleNamespace(id="student-1")
    response = reviews_routes.get_existing_reviews_for_bookings(
        booking_ids=["b1", "b2"],
        current_user=current_user,
        service=_Service(),
    )
    assert response.root == ["b1", "b2"]


@pytest.mark.asyncio
async def test_submit_review_domain_exception():
    class _Service:
        def __init__(self):
            self.db = SimpleNamespace()

        def submit_review_with_tip(self, *_args, **_kwargs):
            raise ValidationException("Invalid rating")

    payload = ReviewSubmitRequest(booking_id="b1", rating=5)
    user = SimpleNamespace(id="student-1", first_name="S", last_name="One")
    with pytest.raises(reviews_routes.HTTPException) as exc:
        await reviews_routes.submit_review(payload=payload, current_user=user, service=_Service())
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_submit_review_success():
    review = SimpleNamespace(
        id="r1",
        rating=5,
        review_text="Great",
        created_at=datetime.now(timezone.utc),
        instructor_service_id="svc1",
    )

    class _Service:
        def __init__(self):
            self.db = SimpleNamespace()

        def submit_review_with_tip(self, *_args, **_kwargs):
            return {"review": review, "tip_status": "succeeded", "tip_client_secret": "secret"}

    payload = ReviewSubmitRequest(booking_id="b1", rating=5, review_text="Great")
    user = SimpleNamespace(id="student-1", first_name="S", last_name="One")
    response = await reviews_routes.submit_review(payload=payload, current_user=user, service=_Service())
    assert response.id == "r1"
    assert response.tip_status == "succeeded"


@pytest.mark.asyncio
async def test_submit_review_unexpected_error_returns_400():
    class _Service:
        def __init__(self):
            self.db = SimpleNamespace()

        def submit_review_with_tip(self, *_args, **_kwargs):
            raise RuntimeError("boom")

    payload = ReviewSubmitRequest(booking_id="b1", rating=5)
    user = SimpleNamespace(id="student-1", first_name="S", last_name="One")
    with pytest.raises(reviews_routes.HTTPException) as exc:
        await reviews_routes.submit_review(payload=payload, current_user=user, service=_Service())
    assert exc.value.status_code == 400


def test_get_instructor_ratings_repository_exception():
    class _Service:
        def get_instructor_ratings(self, *_args, **_kwargs):
            raise RepositoryException("QueuePool timeout")

    with pytest.raises(reviews_routes.HTTPException) as exc:
        reviews_routes.get_instructor_ratings(instructor_id="01HF4G12ABCDEF3456789XYZAB", service=_Service())
    assert exc.value.status_code == 503


def test_get_instructor_ratings_success():
    class _Service:
        def get_instructor_ratings(self, *_args, **_kwargs):
            return {
                "overall": {"rating": 4.8, "total_reviews": 12},
                "by_service": [],
                "confidence_level": "trusted",
            }

    response = reviews_routes.get_instructor_ratings(
        instructor_id="01HF4G12ABCDEF3456789XYZAB",
        service=_Service(),
    )
    assert response.overall["rating"] == 4.8
    assert response.overall["total_reviews"] == 12


def test_get_ratings_batch_handles_min_reviews():
    class _Config:
        min_reviews_to_display = 3

    class _Service:
        config = _Config()

        def get_instructor_ratings(self, instructor_id):
            if instructor_id == "low":
                return {"overall": {"rating": 4.5, "total_reviews": 1}}
            return {"overall": {"rating": 4.9, "total_reviews": 5}}

    payload = RatingsBatchRequest(instructor_ids=["low", "high"])
    response = reviews_routes.get_ratings_batch(payload=payload, service=_Service())
    assert response.results[0].rating is None
    assert response.results[1].rating == 4.9


def test_get_search_rating_basic():
    class _Service:
        def get_rating_for_search_context(self, *_args, **_kwargs):
            return {"primary_rating": 4.7, "review_count": 12, "is_service_specific": False}

    response = reviews_routes.get_search_rating(
        instructor_id="01HF4G12ABCDEF3456789XYZAB", instructor_service_id=None, service=_Service()
    )
    assert response.primary_rating == 4.7
    assert response.review_count == 12


def test_get_recent_reviews_handles_reviewer_errors():
    now = datetime.now(timezone.utc)

    class _Service:
        def get_recent_reviews(self, *_args, **_kwargs):
            return [
                SimpleNamespace(
                    id="r1",
                    rating=5,
                    review_text="Great",
                    created_at=now,
                    instructor_service_id="svc1",
                    student_id="student-1",
                )
            ]

        def count_recent_reviews(self, *_args, **_kwargs):
            return 1

        def get_reviewer_display_name(self, *_args, **_kwargs):
            raise RuntimeError("boom")

    response = reviews_routes.get_recent_reviews(
        instructor_id="01HF4G12ABCDEF3456789XYZAB",
        instructor_service_id=None,
        limit=10,
        page=1,
        min_rating=4,
        rating=5,
        with_text=True,
        service=_Service(),
    )
    assert response.total == 1
    assert response.reviews[0].reviewer_display_name is None


def test_get_recent_reviews_rating_overrides_min():
    now = datetime.now(timezone.utc)

    class _Service:
        def __init__(self):
            self.last_min = None

        def get_recent_reviews(self, *, min_rating, **_kwargs):
            self.last_min = min_rating
            return [
                SimpleNamespace(
                    id="r1",
                    rating=5,
                    review_text="Great",
                    created_at=now,
                    instructor_service_id="svc1",
                    student_id="student-1",
                )
            ]

        def count_recent_reviews(self, *_args, **_kwargs):
            return 1

        def get_reviewer_display_name(self, *_args, **_kwargs):
            return "Student S."

    service = _Service()
    response = reviews_routes.get_recent_reviews(
        instructor_id="01HF4G12ABCDEF3456789XYZAB",
        instructor_service_id=None,
        limit=10,
        page=2,
        min_rating=4,
        rating=5,
        with_text=True,
        service=service,
    )
    assert response.has_prev is True
    assert service.last_min is None


def test_get_review_for_booking_forbidden():
    class _Service:
        def get_review_for_booking(self, *_args, **_kwargs):
            return SimpleNamespace(
                id="r1",
                rating=5,
                review_text="Great",
                created_at=datetime.now(timezone.utc),
                instructor_service_id="svc1",
                student_id="student-2",
            )

    user = SimpleNamespace(id="student-1", first_name="S", last_name="One")
    with pytest.raises(reviews_routes.HTTPException) as exc:
        reviews_routes.get_review_for_booking(
            booking_id="01HF4G12ABCDEF3456789XYZAB",
            current_user=user,
            service=_Service(),
        )
    assert exc.value.status_code == 403


def test_get_review_for_booking_none():
    class _Service:
        def get_review_for_booking(self, *_args, **_kwargs):
            return None

    user = SimpleNamespace(id="student-1", first_name="S", last_name="One")
    response = reviews_routes.get_review_for_booking(
        booking_id="01HF4G12ABCDEF3456789XYZAB",
        current_user=user,
        service=_Service(),
    )
    assert response is None


def test_respond_to_review_error_returns_400():
    class _Service:
        def add_instructor_response(self, *_args, **_kwargs):
            raise RuntimeError("boom")

    user = SimpleNamespace(id="inst-1")
    with pytest.raises(reviews_routes.HTTPException) as exc:
        reviews_routes.respond_to_review(
            review_id="01HF4G12ABCDEF3456789XYZAB",
            response_text="Thanks",
            current_user=user,
            service=_Service(),
        )
    assert exc.value.status_code == 400


def test_respond_to_review_success():
    response_obj = SimpleNamespace(
        id="resp-1",
        review_id="r1",
        instructor_id="instr-1",
        response_text="Thanks",
        created_at=datetime.now(timezone.utc),
    )

    class _Service:
        def add_instructor_response(self, *_args, **_kwargs):
            return response_obj

    user = SimpleNamespace(id="instr-1")
    response = reviews_routes.respond_to_review(
        review_id="01HF4G12ABCDEF3456789XYZAB",
        response_text="Thanks",
        current_user=user,
        service=_Service(),
    )
    assert response.id == "resp-1"
