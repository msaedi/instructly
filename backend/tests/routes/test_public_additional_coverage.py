from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace

from fastapi import HTTPException, Request, Response
import pytest

import app.routes.v1.public as public_routes
from app.schemas.public_availability import (
    PublicDayAvailability,
    PublicInstructorAvailability,
    PublicTimeSlot,
)
from app.schemas.referrals import ReferralSendRequest
from app.services.availability_service import AvailabilityService
import app.services.cache_service as cache_service_module
from app.services.conflict_checker import ConflictChecker
from app.services.instructor_service import InstructorService


def _make_request(headers: dict[str, str] | None = None) -> Request:
    raw_headers = []
    if headers:
        raw_headers = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "headers": raw_headers})


def test_minutes_to_time_str_rollover():
    assert public_routes._minutes_to_time_str(24 * 60) == "00:00"


def test_get_user_now_by_id_uses_availability_service(monkeypatch):
    now = datetime(2025, 1, 10, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(
        public_routes.availability_service_module,
        "get_user_now_by_id",
        lambda *_args, **_kwargs: now,
    )
    assert public_routes._get_user_now_by_id("instr-1", None) == now


def test_dependency_factories_return_services(db):
    availability = public_routes.get_availability_service(db)
    conflict_checker = public_routes.get_conflict_checker(db)
    instructor_service = public_routes.get_instructor_service(db)

    assert isinstance(availability, AvailabilityService)
    assert availability.db is db
    assert isinstance(conflict_checker, ConflictChecker)
    assert conflict_checker.db is db
    assert isinstance(instructor_service, InstructorService)
    assert instructor_service.db is db


def test_get_cache_service_dep_handles_error(monkeypatch, db):
    def _boom(_db):
        raise RuntimeError("cache down")

    monkeypatch.setattr(cache_service_module, "get_cache_service", _boom)
    assert public_routes.get_cache_service_dep(db) is None


def test_apply_min_advance_filter_filters_slots(monkeypatch):
    now_local = datetime(2025, 1, 10, 11, 5, tzinfo=timezone.utc)
    monkeypatch.setattr(public_routes, "_get_user_now_by_id", lambda *_args, **_kwargs: now_local)

    class DummyRepo:
        def __init__(self, min_hours: int) -> None:
            self.profile = SimpleNamespace(min_advance_booking_hours=min_hours)

        def get_by_user_id(self, _instructor_id: str):
            return self.profile

    class DummyAvailabilityService:
        def __init__(self) -> None:
            self.instructor_repository = DummyRepo(1)
            self.db = None

    availability_by_date = {
        "2025-01-09": PublicDayAvailability(
            date="2025-01-09",
            available_slots=[PublicTimeSlot(start_time="09:00", end_time="10:00")],
        ),
        "2025-01-10": PublicDayAvailability(
            date="2025-01-10",
            available_slots=[
                PublicTimeSlot(start_time="09:00", end_time="10:00"),
                PublicTimeSlot(start_time="14:00", end_time="13:00"),
                PublicTimeSlot(start_time="13:00", end_time="14:00"),
            ],
        ),
    }

    total_slots, earliest = public_routes._apply_min_advance_filter(
        DummyAvailabilityService(), "instr-1", availability_by_date
    )
    assert total_slots >= 1
    assert earliest == "2025-01-10"
    assert availability_by_date["2025-01-09"].available_slots == []


def test_apply_min_advance_filter_empty():
    total_slots, earliest = public_routes._apply_min_advance_filter(
        SimpleNamespace(instructor_repository=None, db=None),
        "instr-1",
        {},
    )
    assert total_slots == 0
    assert earliest is None


def test_apply_min_advance_filter_min_hours_zero(monkeypatch):
    now_local = datetime(2025, 1, 10, 11, 5, tzinfo=timezone.utc)
    monkeypatch.setattr(public_routes, "_get_user_now_by_id", lambda *_args, **_kwargs: now_local)

    class DummyRepo:
        def __init__(self):
            self.profile = SimpleNamespace(min_advance_booking_hours=0)

        def get_by_user_id(self, _instructor_id: str):
            return self.profile

    class DummyAvailabilityService:
        def __init__(self) -> None:
            self.instructor_repository = DummyRepo()
            self.db = None

    availability_by_date = {
        "2025-01-10": PublicDayAvailability(
            date="2025-01-10",
            available_slots=[PublicTimeSlot(start_time="09:00", end_time="10:00")],
        ),
        "2025-01-11": PublicDayAvailability(
            date="2025-01-11",
            available_slots=[PublicTimeSlot(start_time="11:00", end_time="12:00")],
        ),
    }

    total_slots, earliest = public_routes._apply_min_advance_filter(
        DummyAvailabilityService(), "instr-1", availability_by_date
    )
    assert total_slots == 2
    assert earliest == "2025-01-10"


def test_create_guest_session_sets_cookie_and_idempotent(monkeypatch):
    monkeypatch.setenv("SITE_MODE", "preview")
    response = Response()
    result = public_routes.create_guest_session(response, _make_request())
    assert result is not None
    set_cookie = response.headers.get("set-cookie", "").lower()
    assert "secure" in set_cookie
    assert "domain=.instainstru.com" in set_cookie

    response = Response()
    result = public_routes.create_guest_session(response, _make_request({"cookie": "guest_id=guest-123"}))
    assert isinstance(result, Response)
    assert result.status_code == 204


def test_public_logout_handles_host_cookie(monkeypatch):
    monkeypatch.setenv("SITE_MODE", "preview")
    monkeypatch.setattr(
        public_routes,
        "session_cookie_candidates",
        lambda *_args, **_kwargs: ["session", "__Host-legacy"],
    )
    response = public_routes.public_logout(Response(), _make_request())
    assert response.status_code == 204


def test_public_logout_logs_audit_when_session_token_present(monkeypatch):
    monkeypatch.setattr(public_routes, "session_cookie_candidates", lambda *_args, **_kwargs: ["session"])
    monkeypatch.setattr(
        public_routes, "decode_access_token", lambda *_args, **_kwargs: {"email": "user@example.com"}
    )
    audit_calls = []

    class DummyAuditService:
        def __init__(self, _db) -> None:
            pass

        def log(self, **kwargs):
            audit_calls.append(kwargs)

    monkeypatch.setattr(public_routes, "AuditService", DummyAuditService)

    response = public_routes.public_logout(
        Response(),
        _make_request({"cookie": "session=token123"}),
        db=SimpleNamespace(),
    )

    assert response.status_code == 204
    assert len(audit_calls) == 1
    assert audit_calls[0]["actor_email"] == "user@example.com"


def test_public_logout_ignores_audit_errors(monkeypatch):
    monkeypatch.setattr(public_routes, "session_cookie_candidates", lambda *_args, **_kwargs: ["session"])
    monkeypatch.setattr(
        public_routes, "decode_access_token", lambda *_args, **_kwargs: {"email": "user@example.com"}
    )

    class FailingAuditService:
        def __init__(self, _db) -> None:
            pass

        def log(self, **_kwargs):
            raise RuntimeError("audit write failed")

    monkeypatch.setattr(public_routes, "AuditService", FailingAuditService)
    warning_messages: list[str] = []
    monkeypatch.setattr(public_routes.logger, "warning", lambda message, *args, **kwargs: warning_messages.append(message))

    response = public_routes.public_logout(
        Response(),
        _make_request({"cookie": "session=token123"}),
        db=SimpleNamespace(),
    )

    assert response.status_code == 204
    assert warning_messages == ["Audit log write failed for logout"]


@pytest.mark.asyncio
async def test_public_availability_summary_branch(monkeypatch):
    user = SimpleNamespace(
        id="instructor-summary",
        first_name="Test",
        last_name="Teacher",
        timezone="America/New_York",
    )

    class DummyInstructorService:
        def get_instructor_user(self, _instructor_id: str):
            return user

    class DummyAvailabilityService:
        def get_week_windows_as_slot_like(self, *_args, **_kwargs):
            return [
                {
                    "specific_date": date.today() + timedelta(days=1),
                    "start_time": time(9, 0),
                    "end_time": time(10, 0),
                },
                {
                    "specific_date": date.today() + timedelta(days=1),
                    "start_time": time(18, 0),
                    "end_time": time(19, 0),
                },
            ]

    class DummyConflictChecker:
        pass

    monkeypatch.setattr(public_routes.settings, "public_availability_detail_level", "summary")
    monkeypatch.setattr(public_routes.settings, "public_availability_show_instructor_name", True)
    start_date = date.today() + timedelta(days=1)
    response = Response()

    result = await public_routes.get_instructor_public_availability(
        instructor_id=user.id,
        request=_make_request(),
        response_obj=response,
        start_date=start_date,
        end_date=start_date,
        availability_service=DummyAvailabilityService(),
        conflict_checker=DummyConflictChecker(),
        instructor_service=DummyInstructorService(),
        cache_service=None,
        db=None,
    )

    assert result.detail_level == "summary"
    assert result.total_available_days == 1
    assert result.availability_summary is not None


@pytest.mark.asyncio
async def test_public_availability_validation_errors(monkeypatch):
    user = SimpleNamespace(
        id="instructor-validate",
        first_name="Test",
        last_name="Teacher",
        timezone="America/New_York",
    )

    class DummyInstructorService:
        def get_instructor_user(self, _instructor_id: str):
            return user

    class DummyAvailabilityService:
        pass

    class DummyConflictChecker:
        pass

    start_date = date(2025, 1, 10)
    monkeypatch.setattr(public_routes, "get_user_today", lambda _user: start_date)

    with pytest.raises(HTTPException) as exc:
        await public_routes.get_instructor_public_availability(
            instructor_id=user.id,
            request=_make_request(),
            response_obj=Response(),
            start_date=start_date - timedelta(days=1),
            end_date=start_date,
            availability_service=DummyAvailabilityService(),
            conflict_checker=DummyConflictChecker(),
            instructor_service=DummyInstructorService(),
            cache_service=None,
            db=None,
        )
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        await public_routes.get_instructor_public_availability(
            instructor_id=user.id,
            request=_make_request(),
            response_obj=Response(),
            start_date=start_date,
            end_date=start_date - timedelta(days=1),
            availability_service=DummyAvailabilityService(),
            conflict_checker=DummyConflictChecker(),
            instructor_service=DummyInstructorService(),
            cache_service=None,
            db=None,
        )
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        await public_routes.get_instructor_public_availability(
            instructor_id=user.id,
            request=_make_request(),
            response_obj=Response(),
            start_date=start_date,
            end_date=start_date + timedelta(days=91),
            availability_service=DummyAvailabilityService(),
            conflict_checker=DummyConflictChecker(),
            instructor_service=DummyInstructorService(),
            cache_service=None,
            db=None,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_public_availability_instructor_not_found():
    class DummyInstructorService:
        def get_instructor_user(self, _instructor_id: str):
            raise RuntimeError("not found")

    class DummyAvailabilityService:
        pass

    class DummyConflictChecker:
        pass

    start_date = date.today() + timedelta(days=1)
    with pytest.raises(HTTPException) as exc:
        await public_routes.get_instructor_public_availability(
            instructor_id="missing",
            request=_make_request(),
            response_obj=Response(),
            start_date=start_date,
            end_date=start_date,
            availability_service=DummyAvailabilityService(),
            conflict_checker=DummyConflictChecker(),
            instructor_service=DummyInstructorService(),
            cache_service=None,
            db=None,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_public_availability_cache_hit_etag_304(monkeypatch):
    user = SimpleNamespace(
        id="instructor-1",
        first_name="Test",
        last_name="Teacher",
        timezone="America/New_York",
    )

    class DummyInstructorService:
        def get_instructor_user(self, _instructor_id: str):
            return user

    class DummyAvailabilityService:
        def __init__(self) -> None:
            self.instructor_repository = SimpleNamespace(
                get_by_user_id=lambda _id: SimpleNamespace(min_advance_booking_hours=0)
            )
            self.db = None

    class DummyConflictChecker:
        pass

    today = date.today() + timedelta(days=1)
    availability_by_date = {
        today.isoformat(): PublicDayAvailability(
            date=today.isoformat(),
            available_slots=[PublicTimeSlot(start_time="09:00", end_time="10:00")],
        )
    }
    cached = PublicInstructorAvailability(
        instructor_id=user.id,
        instructor_first_name="Test",
        instructor_last_initial="T",
        detail_level="full",
        availability_by_date=availability_by_date,
        has_availability=True,
        total_available_slots=1,
        earliest_available_date=today.isoformat(),
        timezone="America/New_York",
    )

    class DummyCache:
        async def get(self, _key: str):
            return cached.model_dump(exclude_none=True)

    request = _make_request()
    response = Response()
    await public_routes.get_instructor_public_availability(
        instructor_id=user.id,
        request=request,
        response_obj=response,
        start_date=today,
        end_date=today,
        availability_service=DummyAvailabilityService(),
        conflict_checker=DummyConflictChecker(),
        instructor_service=DummyInstructorService(),
        cache_service=DummyCache(),
        db=None,
    )
    etag = response.headers.get("ETag")
    assert etag

    request = _make_request({"If-None-Match": etag})
    response = Response()
    await public_routes.get_instructor_public_availability(
        instructor_id=user.id,
        request=request,
        response_obj=response,
        start_date=today,
        end_date=today,
        availability_service=DummyAvailabilityService(),
        conflict_checker=DummyConflictChecker(),
        instructor_service=DummyInstructorService(),
        cache_service=DummyCache(),
        db=None,
    )
    assert response.status_code == 304


@pytest.mark.asyncio
async def test_public_availability_etag_on_cache_miss(monkeypatch):
    user = SimpleNamespace(
        id="instructor-2",
        first_name="Test",
        last_name="Teacher",
        timezone="America/New_York",
    )

    class DummyInstructorService:
        def get_instructor_user(self, _instructor_id: str):
            return user

    class DummyAvailabilityService:
        def get_week_windows_as_slot_like(self, *_args, **_kwargs):
            return [{"specific_date": date.today() + timedelta(days=1)}]

    class DummyConflictChecker:
        pass

    monkeypatch.setattr(public_routes.settings, "public_availability_detail_level", "minimal")
    start_date = date.today() + timedelta(days=1)
    request = _make_request()
    response = Response()
    await public_routes.get_instructor_public_availability(
        instructor_id=user.id,
        request=request,
        response_obj=response,
        start_date=start_date,
        end_date=start_date,
        availability_service=DummyAvailabilityService(),
        conflict_checker=DummyConflictChecker(),
        instructor_service=DummyInstructorService(),
        cache_service=None,
        db=None,
    )
    etag = response.headers.get("ETag")
    assert etag

    request = _make_request({"If-None-Match": etag})
    response = Response()
    await public_routes.get_instructor_public_availability(
        instructor_id=user.id,
        request=request,
        response_obj=response,
        start_date=start_date,
        end_date=start_date,
        availability_service=DummyAvailabilityService(),
        conflict_checker=DummyConflictChecker(),
        instructor_service=DummyInstructorService(),
        cache_service=None,
        db=None,
    )
    assert response.status_code == 304


@pytest.mark.asyncio
async def test_send_referral_invites_validation_and_partial_failure(monkeypatch):
    class StubEmailService:
        def __init__(self, _db) -> None:
            pass

        def validate_email_config(self) -> None:
            return None

        def send_referral_invite(self, *, to_email: str, referral_link: str, inviter_name: str):
            if to_email == "fail@example.com":
                raise RuntimeError("smtp down")

    monkeypatch.setattr(public_routes, "EmailService", StubEmailService)

    payload = ReferralSendRequest(
        emails=["ok@example.com", "fail@example.com"],
        referral_link="https://instainstru.com/ref/ABC",
        from_name="Tester",
    )
    mock_request = _make_request()
    result = await public_routes.send_referral_invites(request=mock_request, payload=payload, db=None)
    assert result.sent == 1
    assert result.failed == 1


@pytest.mark.asyncio
async def test_send_referral_invites_empty_and_config_error(monkeypatch):
    mock_request = _make_request()
    payload = ReferralSendRequest(emails=[], referral_link="https://instainstru.com/ref/ABC")
    with pytest.raises(HTTPException) as exc:
        await public_routes.send_referral_invites(request=mock_request, payload=payload, db=None)
    assert exc.value.status_code == 400

    class FailingEmailService:
        def __init__(self, _db) -> None:
            pass

        def validate_email_config(self) -> None:
            raise RuntimeError("missing key")

    monkeypatch.setattr(public_routes, "EmailService", FailingEmailService)
    payload = ReferralSendRequest(
        emails=["ok@example.com"],
        referral_link="https://instainstru.com/ref/ABC",
        from_name=None,
    )
    with pytest.raises(HTTPException) as exc:
        await public_routes.send_referral_invites(request=mock_request, payload=payload, db=None)
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_send_referral_invites_max_emails_exceeded(monkeypatch):
    """Backend validation: reject more than 10 emails per request."""
    mock_request = _make_request()
    # Generate 11 valid emails (exceeds MAX_REFERRAL_EMAILS_PER_REQUEST)
    emails = [f"user{i}@example.com" for i in range(11)]
    payload = ReferralSendRequest(
        emails=emails,
        referral_link="https://instainstru.com/ref/ABC",
        from_name="Tester",
    )
    with pytest.raises(HTTPException) as exc:
        await public_routes.send_referral_invites(request=mock_request, payload=payload, db=None)
    assert exc.value.status_code == 400
    assert "Maximum 10 emails" in exc.value.detail


@pytest.mark.asyncio
async def test_send_referral_invites_exactly_10_emails_allowed(monkeypatch):
    """Backend validation: exactly 10 emails should be allowed."""
    class StubEmailService:
        def __init__(self, _db) -> None:
            pass

        def validate_email_config(self) -> None:
            return None

        def send_referral_invite(self, *, to_email: str, referral_link: str, inviter_name: str):
            pass

    monkeypatch.setattr(public_routes, "EmailService", StubEmailService)

    mock_request = _make_request()
    # Generate exactly 10 valid emails (at the limit)
    emails = [f"user{i}@example.com" for i in range(10)]
    payload = ReferralSendRequest(
        emails=emails,
        referral_link="https://instainstru.com/ref/ABC",
        from_name="Tester",
    )
    result = await public_routes.send_referral_invites(request=mock_request, payload=payload, db=None)
    assert result.sent == 10
    assert result.failed == 0


@pytest.mark.asyncio
async def test_send_referral_invites_rejects_all_invalid_email_formats():
    payload = SimpleNamespace(
        emails=["not-an-email"],
        referral_link="https://instainstru.com/ref/ABC",
        from_name="Tester",
    )

    with pytest.raises(HTTPException) as exc:
        await public_routes.send_referral_invites(request=_make_request(), payload=payload, db=None)

    assert exc.value.status_code == 400
    assert exc.value.detail == "No valid email addresses provided"


@pytest.mark.asyncio
async def test_send_referral_invites_counts_invalid_emails_as_failures(monkeypatch):
    class StubEmailService:
        def __init__(self, _db) -> None:
            pass

        def validate_email_config(self) -> None:
            return None

        def send_referral_invite(self, *, to_email: str, referral_link: str, inviter_name: str):
            return None

    monkeypatch.setattr(public_routes, "EmailService", StubEmailService)
    payload = SimpleNamespace(
        emails=["ok@example.com", "bad-email"],
        referral_link="https://instainstru.com/ref/ABC",
        from_name="Tester",
    )
    result = await public_routes.send_referral_invites(request=_make_request(), payload=payload, db=None)

    assert result.sent == 1
    assert result.failed == 1
    assert result.errors[0].email == "invalid-email@example.com"
    assert "bad-email" in result.errors[0].error


@pytest.mark.asyncio
async def test_send_referral_invites_tolerates_error_detail_serialization_failure(monkeypatch):
    class FailingEmailService:
        def __init__(self, _db) -> None:
            pass

        def validate_email_config(self) -> None:
            return None

        def send_referral_invite(self, *, to_email: str, referral_link: str, inviter_name: str):
            raise RuntimeError("smtp down")

    def _boom_referral_error(*_args, **_kwargs):
        raise RuntimeError("serialization failure")

    monkeypatch.setattr(public_routes, "EmailService", FailingEmailService)
    monkeypatch.setattr(public_routes, "ReferralSendError", _boom_referral_error)

    payload = ReferralSendRequest(
        emails=["fail@example.com"],
        referral_link="https://instainstru.com/ref/ABC",
        from_name="Tester",
    )
    result = await public_routes.send_referral_invites(request=_make_request(), payload=payload, db=None)

    assert result.sent == 0
    assert result.failed == 1
    assert result.errors == []


@pytest.mark.asyncio
async def test_next_available_slot_found_and_not_found(monkeypatch):
    user = SimpleNamespace(
        id="instructor-next",
        first_name="Test",
        last_name="Teacher",
        timezone="America/New_York",
    )

    class DummyInstructorService:
        def get_instructor_user(self, _instructor_id: str):
            return user

    class DummyConflictChecker:
        def check_blackout_date(self, _instructor_id: str, _date_value: date):
            return False

    class DummyAvailabilityService:
        def compute_public_availability(self, *_args, **_kwargs):
            return {
                date.today().isoformat(): [
                    (time(9, 0), time(11, 0)),
                ]
            }

    response = Response()
    result = await public_routes.get_next_available_slot(
        instructor_id=user.id,
        response_obj=response,
        duration_minutes=30,
        availability_service=DummyAvailabilityService(),
        conflict_checker=DummyConflictChecker(),
        instructor_service=DummyInstructorService(),
        db=None,
    )
    assert result.found is True
    assert response.headers.get("Cache-Control") == "public, max-age=120"

    class EmptyAvailabilityService:
        def compute_public_availability(self, *_args, **_kwargs):
            return {}

    response = Response()
    result = await public_routes.get_next_available_slot(
        instructor_id=user.id,
        response_obj=response,
        duration_minutes=30,
        availability_service=EmptyAvailabilityService(),
        conflict_checker=DummyConflictChecker(),
        instructor_service=DummyInstructorService(),
        db=None,
    )
    assert result.found is False
    assert response.headers.get("Cache-Control") == "public, max-age=60"


@pytest.mark.asyncio
async def test_next_available_slot_skips_blackout_day(monkeypatch):
    user = SimpleNamespace(
        id="instructor-blackout",
        first_name="Test",
        last_name="Teacher",
        timezone="America/New_York",
    )

    class DummyInstructorService:
        def get_instructor_user(self, _instructor_id: str):
            return user

    class DummyConflictChecker:
        def __init__(self) -> None:
            self.calls = 0

        def check_blackout_date(self, _instructor_id: str, _date_value: date):
            self.calls += 1
            return self.calls == 1

    class DummyAvailabilityService:
        def compute_public_availability(self, _instructor_id: str, start: date, _end: date):
            return {start.isoformat(): [(time(10, 0), time(11, 30))]}

    response = Response()
    result = await public_routes.get_next_available_slot(
        instructor_id=user.id,
        response_obj=response,
        duration_minutes=60,
        availability_service=DummyAvailabilityService(),
        conflict_checker=DummyConflictChecker(),
        instructor_service=DummyInstructorService(),
        db=None,
    )

    assert result.found is True
    assert response.headers.get("Cache-Control") == "public, max-age=120"


@pytest.mark.asyncio
async def test_next_available_slot_instructor_not_found():
    class DummyInstructorService:
        def get_instructor_user(self, _instructor_id: str):
            raise RuntimeError("missing")

    class DummyConflictChecker:
        def check_blackout_date(self, _instructor_id: str, _date_value: date):
            return False

    class DummyAvailabilityService:
        def compute_public_availability(self, *_args, **_kwargs):
            return {}

    with pytest.raises(HTTPException) as exc:
        await public_routes.get_next_available_slot(
            instructor_id="missing",
            response_obj=Response(),
            duration_minutes=30,
            availability_service=DummyAvailabilityService(),
            conflict_checker=DummyConflictChecker(),
            instructor_service=DummyInstructorService(),
            db=None,
        )
    assert exc.value.status_code == 404
