"""Coverage tests for public routes — cache hit with ETag 304, detail level branches, blackout dates."""

from __future__ import annotations

from datetime import date, time, timedelta
from types import SimpleNamespace

from fastapi import Response
from fastapi.requests import Request
import pytest

import app.routes.v1.public as public_routes


def _make_request(headers: dict[str, str] | None = None) -> Request:
    raw_headers = []
    if headers:
        raw_headers = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "headers": raw_headers})


# ---- L186: create_guest_session idempotent 204 when cookie already present ----
def test_create_guest_session_idempotent():
    request = _make_request({"cookie": "guest_id=existing123"})
    response = Response()
    result = public_routes.create_guest_session(response, request)
    assert isinstance(result, Response)
    assert result.status_code == 204


# ---- L205: site_mode preview/prod secure cookie ----
def test_create_guest_session_preview_mode(monkeypatch):
    monkeypatch.setenv("SITE_MODE", "preview")
    request = _make_request()
    response = Response()
    result = public_routes.create_guest_session(response, request)
    assert hasattr(result, "guest_id")
    set_cookie = response.headers.get("set-cookie", "").lower()
    assert "secure" in set_cookie


# ---- L250: public_availability_detail_level minimal branch ----
@pytest.mark.asyncio
async def test_availability_minimal_no_slots(monkeypatch):
    user = SimpleNamespace(
        id="instr-min",
        first_name="Test",
        last_name="T",
        timezone="America/New_York",
    )

    class DummyInstructorService:
        def get_instructor_user(self, _id: str):
            return user

    class DummyAvailabilityService:
        def get_week_windows_as_slot_like(self, *_args, **_kwargs):
            return []

    monkeypatch.setattr(public_routes.settings, "public_availability_detail_level", "minimal")
    monkeypatch.setattr(public_routes.settings, "public_availability_show_instructor_name", False)
    start_date = date.today() + timedelta(days=1)

    result = await public_routes.get_instructor_public_availability(
        instructor_id=user.id,
        request=_make_request(),
        response_obj=Response(),
        start_date=start_date,
        end_date=start_date,
        availability_service=DummyAvailabilityService(),
        conflict_checker=SimpleNamespace(),
        instructor_service=DummyInstructorService(),
        cache_service=None,
        db=None,
    )

    assert result.detail_level == "minimal"
    assert result.has_availability is False
    assert result.instructor_first_name is None
    assert result.instructor_last_initial is None


# ---- L257, L259, L264: full detail level with blackout dates ----
@pytest.mark.asyncio
async def test_availability_full_with_blackout(monkeypatch):
    user = SimpleNamespace(
        id="instr-full",
        first_name="Jane",
        last_name="D",
        timezone="America/New_York",
    )
    start_date = date.today() + timedelta(days=1)

    class DummyInstructorService:
        def get_instructor_user(self, _id: str):
            return user

    class DummyAvailabilityService:
        def __init__(self):
            self.instructor_repository = SimpleNamespace(
                get_by_user_id=lambda _id: SimpleNamespace(min_advance_booking_hours=0)
            )
            self.db = None

        def get_blackout_dates(self, _instructor_id: str):
            return [SimpleNamespace(date=start_date)]

        def compute_public_availability(self, *_args, **_kwargs):
            return {}

    monkeypatch.setattr(public_routes.settings, "public_availability_detail_level", "full")
    monkeypatch.setattr(public_routes.settings, "public_availability_show_instructor_name", True)
    monkeypatch.setattr(public_routes.settings, "public_availability_days", 7)

    result = await public_routes.get_instructor_public_availability(
        instructor_id=user.id,
        request=_make_request(),
        response_obj=Response(),
        start_date=start_date,
        end_date=start_date,
        availability_service=DummyAvailabilityService(),
        conflict_checker=SimpleNamespace(),
        instructor_service=DummyInstructorService(),
        cache_service=None,
        db=None,
    )

    assert result.detail_level == "full"
    day_data = result.availability_by_date[start_date.isoformat()]
    assert day_data.is_blackout is True


# ---- L278-286: full detail cache write failure tolerance ----
@pytest.mark.asyncio
async def test_availability_full_cache_write_fails_gracefully(monkeypatch):
    user = SimpleNamespace(
        id="instr-cache-err",
        first_name="Test",
        last_name="T",
        timezone="America/New_York",
    )
    start_date = date.today() + timedelta(days=1)

    class DummyInstructorService:
        def get_instructor_user(self, _id: str):
            return user

    class DummyAvailabilityService:
        def __init__(self):
            self.instructor_repository = SimpleNamespace(
                get_by_user_id=lambda _id: SimpleNamespace(min_advance_booking_hours=0)
            )
            self.db = None

        def get_blackout_dates(self, _instructor_id: str):
            return []

        def compute_public_availability(self, *_args, **_kwargs):
            return {
                start_date.isoformat(): [(time(9, 0), time(10, 0))],
            }

    class FailingCache:
        async def get(self, _key: str):
            return None

        async def set(self, _key: str, _data, ttl=None):
            raise RuntimeError("cache write failed")

    monkeypatch.setattr(public_routes.settings, "public_availability_detail_level", "full")
    monkeypatch.setattr(public_routes.settings, "public_availability_show_instructor_name", True)
    monkeypatch.setattr(public_routes.settings, "public_availability_days", 7)
    monkeypatch.setattr(public_routes.settings, "public_availability_cache_ttl", 120)

    result = await public_routes.get_instructor_public_availability(
        instructor_id=user.id,
        request=_make_request(),
        response_obj=Response(),
        start_date=start_date,
        end_date=start_date,
        availability_service=DummyAvailabilityService(),
        conflict_checker=SimpleNamespace(),
        instructor_service=DummyInstructorService(),
        cache_service=FailingCache(),
        db=None,
    )

    assert result.total_available_slots >= 0


# ---- L713, L724: next-available slot duration filter ----
@pytest.mark.asyncio
async def test_next_available_slot_skip_short_duration(monkeypatch):
    user = SimpleNamespace(
        id="instr-short",
        first_name="Test",
        last_name="T",
        timezone="America/New_York",
    )

    class DummyInstructorService:
        def get_instructor_user(self, _id: str):
            return user

    class DummyConflictChecker:
        def check_blackout_date(self, _id: str, _d: date):
            return False

    class DummyAvailabilityService:
        def compute_public_availability(self, *_args, **_kwargs):
            # Only 30-min slot, request 60
            return {
                date.today().isoformat(): [(time(9, 0), time(9, 30))],
            }

    monkeypatch.setattr(public_routes.settings, "public_availability_days", 1)

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
    assert result.found is False


# ---- Cache hit with exception during cache read ----
@pytest.mark.asyncio
async def test_availability_cache_read_error_falls_through(monkeypatch):
    user = SimpleNamespace(
        id="instr-cache-read-err",
        first_name="Test",
        last_name="T",
        timezone="America/New_York",
    )
    start_date = date.today() + timedelta(days=1)

    class DummyInstructorService:
        def get_instructor_user(self, _id: str):
            return user

    class DummyAvailabilityService:
        def get_week_windows_as_slot_like(self, *_args, **_kwargs):
            return []

    class FailingCache:
        async def get(self, _key: str):
            raise RuntimeError("cache read failed")

    monkeypatch.setattr(public_routes.settings, "public_availability_detail_level", "minimal")

    result = await public_routes.get_instructor_public_availability(
        instructor_id=user.id,
        request=_make_request(),
        response_obj=Response(),
        start_date=start_date,
        end_date=start_date,
        availability_service=DummyAvailabilityService(),
        conflict_checker=SimpleNamespace(),
        instructor_service=DummyInstructorService(),
        cache_service=FailingCache(),
        db=None,
    )

    assert result.detail_level == "minimal"


# ---- Logout exp as string ----
def test_public_logout_exp_string(monkeypatch):
    monkeypatch.setattr(public_routes, "session_cookie_candidates", lambda *_args, **_kwargs: ["session"])
    monkeypatch.setattr(
        public_routes,
        "decode_access_token",
        lambda *_args, **_kwargs: {"email": "u@e.com", "jti": "j1", "exp": "9999999999"},
    )
    revoked: list = []

    class DummyBlacklistService:
        def revoke_token_sync(self, jti: str, exp: int, **_kwargs) -> bool:
            revoked.append((jti, exp))
            return True

    class DummyAuditService:
        def __init__(self, _db):
            pass

        def log(self, **_kwargs):
            pass

    monkeypatch.setattr(public_routes, "TokenBlacklistService", lambda: DummyBlacklistService())
    monkeypatch.setattr(public_routes, "AuditService", DummyAuditService)

    resp = public_routes.public_logout(
        Response(), _make_request({"cookie": "session=tok"}), db=SimpleNamespace()
    )
    assert resp.status_code == 204
    assert revoked == [("j1", 9999999999)]


# ---- Logout exp as float ----
def test_public_logout_exp_float(monkeypatch):
    monkeypatch.setattr(public_routes, "session_cookie_candidates", lambda *_args, **_kwargs: ["session"])
    monkeypatch.setattr(
        public_routes,
        "decode_access_token",
        lambda *_args, **_kwargs: {"email": "u@e.com", "jti": "j2", "exp": 9999999999.5},
    )
    revoked: list = []

    class DummyBlacklistService:
        def revoke_token_sync(self, jti: str, exp: int, **_kwargs) -> bool:
            revoked.append((jti, exp))
            return True

    class DummyAuditService:
        def __init__(self, _db):
            pass

        def log(self, **_kwargs):
            pass

    monkeypatch.setattr(public_routes, "TokenBlacklistService", lambda: DummyBlacklistService())
    monkeypatch.setattr(public_routes, "AuditService", DummyAuditService)

    resp = public_routes.public_logout(
        Response(), _make_request({"cookie": "session=tok"}), db=SimpleNamespace()
    )
    assert resp.status_code == 204
    assert revoked == [("j2", 9999999999)]


# ---- Logout exp as invalid string ----
def test_public_logout_exp_invalid_string(monkeypatch):
    monkeypatch.setattr(public_routes, "session_cookie_candidates", lambda *_args, **_kwargs: ["session"])
    monkeypatch.setattr(
        public_routes,
        "decode_access_token",
        lambda *_args, **_kwargs: {"email": "u@e.com", "jti": "j3", "exp": "not_a_number"},
    )
    revoked: list = []

    class DummyBlacklistService:
        def revoke_token_sync(self, jti: str, exp: int, **_kwargs) -> bool:
            revoked.append((jti, exp))
            return True

    class DummyAuditService:
        def __init__(self, _db):
            pass

        def log(self, **_kwargs):
            pass

    monkeypatch.setattr(public_routes, "TokenBlacklistService", lambda: DummyBlacklistService())
    monkeypatch.setattr(public_routes, "AuditService", DummyAuditService)

    resp = public_routes.public_logout(
        Response(), _make_request({"cookie": "session=tok"}), db=SimpleNamespace()
    )
    assert resp.status_code == 204
    # exp_ts is None so blacklist is skipped
    assert revoked == []


# ---- Logout revoke_token_sync returns falsy → warning logged ----
def test_public_logout_revoke_fails(monkeypatch):
    monkeypatch.setattr(public_routes, "session_cookie_candidates", lambda *_args, **_kwargs: ["session"])
    monkeypatch.setattr(
        public_routes,
        "decode_access_token",
        lambda *_args, **_kwargs: {"email": "u@e.com", "jti": "j4", "exp": 9999999999},
    )
    warnings_logged: list = []

    class DummyBlacklistService:
        def revoke_token_sync(self, jti: str, exp: int, **_kwargs):
            return False  # revocation failed

    class DummyAuditService:
        def __init__(self, _db):
            pass

        def log(self, **_kwargs):
            pass

    monkeypatch.setattr(public_routes, "TokenBlacklistService", lambda: DummyBlacklistService())
    monkeypatch.setattr(public_routes, "AuditService", DummyAuditService)
    monkeypatch.setattr(
        public_routes.logger, "warning",
        lambda msg, *args, **kwargs: warnings_logged.append(msg),
    )

    resp = public_routes.public_logout(
        Response(), _make_request({"cookie": "session=tok"}), db=SimpleNamespace()
    )
    assert resp.status_code == 204
    assert any("blacklist" in m.lower() for m in warnings_logged)
