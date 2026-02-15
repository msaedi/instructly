from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi import HTTPException, Response
from fastapi.security import OAuth2PasswordRequestForm
import pytest

from app.auth import get_password_hash
from app.core.exceptions import ConflictException
from app.routes.v1 import auth as auth_routes
from app.schemas.security import PasswordChangeRequest


class _DummyRequest:
    def __init__(self, *, form_data=None, headers=None, cookies=None, client_host="127.0.0.1"):
        self._form_data = form_data or {}
        self.headers = headers or {}
        self.cookies = cookies or {}
        self.client = SimpleNamespace(host=client_host)

    async def form(self):
        return self._form_data


class _BrokenRequest:
    async def form(self):
        raise RuntimeError("boom")


class _StubCache:
    def __init__(self, initial=None):
        self._store = {"known_devices:user": initial} if initial is not None else {}
        self.last_ttl = None

    async def get(self, key):
        return self._store.get(key)

    async def set(self, key, value, ttl=None):
        self._store[key] = value
        self.last_ttl = ttl

    async def delete(self, key):
        return self._store.pop(key, None) is not None


class _StubAuthService:
    def __init__(self, user_data=None, user_obj=None):
        self._user_data = user_data
        self._user_obj = user_obj

    def fetch_user_for_auth(self, _email):
        return self._user_data

    def release_connection(self):
        return None

    def get_current_user(self, identifier=None, *, email=None):
        return self._user_obj


class _StubRegisterService:
    def __init__(self, *, user=None, exc=None):
        self._user = user
        self._exc = exc

    def register_user(self, **_kwargs):
        if self._exc:
            raise self._exc
        return self._user


class _StubLockout:
    def __init__(self, locked=False):
        self.locked = locked

    async def check_lockout(self, _email):
        return self.locked, {"message": "locked", "retry_after": 5}

    async def record_failure(self, _email):
        return None

    async def reset(self, _email):
        return None


class _StubRateLimiter:
    def __init__(self, allowed=True):
        self.allowed = allowed

    async def check(self, _email):
        return self.allowed, {"message": "rate", "retry_after": 5}

    async def record_attempt(self, _email):
        return None

    async def reset(self, _email):
        return None


class _StubCaptcha:
    def __init__(self, required=False, valid=True):
        self.required = required
        self.valid = valid

    async def is_captcha_required(self, _email):
        return self.required

    async def verify(self, _token, _client_ip):
        return self.valid


@asynccontextmanager
async def _noop_slot():
    yield


@pytest.mark.asyncio
async def test_extract_captcha_token_success_and_failure():
    req = _DummyRequest(form_data={"captcha_token": "abc"})
    assert await auth_routes._extract_captcha_token(req) == "abc"
    assert await auth_routes._extract_captcha_token(_BrokenRequest()) is None


@pytest.mark.asyncio
async def test_maybe_send_new_device_login_notification_paths(monkeypatch):
    req = _DummyRequest(headers={"user-agent": "agent"})
    cache = _StubCache()

    await auth_routes._maybe_send_new_device_login_notification(
        user_id=None, request=req, cache_service=cache
    )
    assert cache._store == {}

    fingerprint = auth_routes._device_fingerprint("127.0.0.1", "agent")
    cache_known = _StubCache(initial=[fingerprint])
    await auth_routes._maybe_send_new_device_login_notification(
        user_id="user", request=req, cache_service=cache_known
    )
    assert cache_known._store["known_devices:user"] == [fingerprint]

    def _boom(**_kwargs):
        raise RuntimeError("notify failed")

    monkeypatch.setattr(auth_routes, "_send_new_device_login_notification_sync", _boom)
    cache_empty = _StubCache()
    await auth_routes._maybe_send_new_device_login_notification(
        user_id="user", request=req, cache_service=cache_empty
    )
    assert cache_empty.last_ttl == auth_routes.KNOWN_DEVICE_TTL_SECONDS


@pytest.mark.asyncio
async def test_maybe_send_new_device_trims_known_devices(monkeypatch):
    monkeypatch.setattr(auth_routes, "_send_new_device_login_notification_sync", lambda **_k: None)

    req = _DummyRequest(headers={"user-agent": "agent"})
    initial = [f"dev{i}" for i in range(auth_routes.KNOWN_DEVICE_MAX)]
    cache = _StubCache(initial=initial)

    await auth_routes._maybe_send_new_device_login_notification(
        user_id="user", request=req, cache_service=cache
    )

    stored = cache._store["known_devices:user"]
    assert len(stored) == auth_routes.KNOWN_DEVICE_MAX


def test_send_new_device_login_notification_sync_closes_db(monkeypatch):
    closed = {"count": 0}

    class _StubDb:
        def close(self):
            closed["count"] += 1

    class _StubNotificationService:
        def __init__(self):
            self._owns_db = True
            self.db = _StubDb()

        def send_new_device_login_notification(self, **_kwargs):
            return None

    monkeypatch.setattr(
        "app.services.notification_service.NotificationService",
        _StubNotificationService,
    )

    auth_routes._send_new_device_login_notification_sync(
        user_id="user",
        ip_address="127.0.0.1",
        user_agent="agent",
        login_time=datetime.now(timezone.utc),
    )
    assert closed["count"] == 1


def test_send_password_changed_notification_sync_closes_db(monkeypatch):
    closed = {"count": 0}

    class _StubDb:
        def close(self):
            closed["count"] += 1

    class _StubNotificationService:
        def __init__(self):
            self._owns_db = True
            self.db = _StubDb()

        def send_password_changed_notification(self, **_kwargs):
            return None

    monkeypatch.setattr(
        "app.services.notification_service.NotificationService",
        _StubNotificationService,
    )

    auth_routes._send_password_changed_notification_sync(
        user_id="user", changed_at=datetime.now(timezone.utc)
    )
    assert closed["count"] == 1


def test_should_trust_device_paths(monkeypatch):
    req_cookie = SimpleNamespace(cookies={"tfa_trusted": "1"}, headers={})
    assert auth_routes._should_trust_device(req_cookie) is True

    req_header = SimpleNamespace(cookies={}, headers={"X-Trusted-Bypass": "true"})
    monkeypatch.setattr(auth_routes.settings, "environment", "local", raising=False)
    assert auth_routes._should_trust_device(req_header) is True

    monkeypatch.setattr(auth_routes.settings, "environment", "production", raising=False)
    assert auth_routes._should_trust_device(req_header) is False


def test_issue_two_factor_challenge():
    user = SimpleNamespace(email="user@example.com", totp_enabled=True)
    request = SimpleNamespace(cookies={}, headers={})
    response = auth_routes._issue_two_factor_challenge_if_needed(user, request)
    assert response is not None
    assert response.requires_2fa is True

    user_disabled = SimpleNamespace(email="user@example.com", totp_enabled=False)
    assert auth_routes._issue_two_factor_challenge_if_needed(user_disabled, request) is None


def test_issue_two_factor_trusted_device_returns_none():
    user = SimpleNamespace(email="user@example.com", totp_enabled=True)
    request = SimpleNamespace(cookies={"tfa_trusted": "1"}, headers={})
    assert auth_routes._issue_two_factor_challenge_if_needed(user, request) is None


def test_issue_two_factor_with_extra_claims():
    user = SimpleNamespace(email="user@example.com", totp_enabled=True)
    request = SimpleNamespace(cookies={}, headers={})
    response = auth_routes._issue_two_factor_challenge_if_needed(
        user, request, extra_claims={"guest_session_id": "guest"}
    )
    assert response is not None
    assert response.requires_2fa is True


@pytest.mark.asyncio
async def test_login_locked_out(monkeypatch):
    monkeypatch.setattr(auth_routes, "account_lockout", _StubLockout(locked=True))
    monkeypatch.setattr(auth_routes, "captcha_verifier", _StubCaptcha(required=False))
    monkeypatch.setattr(auth_routes, "account_rate_limiter", _StubRateLimiter(allowed=True))
    monkeypatch.setattr(auth_routes, "login_slot", lambda: _noop_slot())

    auth_service = _StubAuthService(user_data=None)
    request = _DummyRequest()
    response = Response()
    form = OAuth2PasswordRequestForm(
        username="user@example.com",
        password="pass",
        scope="",
        client_id=None,
        client_secret=None,
    )

    with pytest.raises(HTTPException) as exc:
        await auth_routes.login(request, response, form, auth_service, cache_service=object())
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_login_captcha_required_missing_token(monkeypatch):
    monkeypatch.setattr(auth_routes, "account_lockout", _StubLockout(locked=False))
    monkeypatch.setattr(auth_routes, "captcha_verifier", _StubCaptcha(required=True))
    monkeypatch.setattr(auth_routes, "account_rate_limiter", _StubRateLimiter(allowed=True))
    monkeypatch.setattr(auth_routes, "login_slot", lambda: _noop_slot())

    auth_service = _StubAuthService(user_data=None)
    request = _DummyRequest(form_data={})
    response = Response()
    form = OAuth2PasswordRequestForm(
        username="user@example.com",
        password="pass",
        scope="",
        client_id=None,
        client_secret=None,
    )

    with pytest.raises(HTTPException) as exc:
        await auth_routes.login(request, response, form, auth_service, cache_service=object())
    assert exc.value.status_code == 428


@pytest.mark.asyncio
async def test_login_captcha_failed(monkeypatch):
    monkeypatch.setattr(auth_routes, "account_lockout", _StubLockout(locked=False))
    monkeypatch.setattr(auth_routes, "captcha_verifier", _StubCaptcha(required=True, valid=False))
    monkeypatch.setattr(auth_routes, "account_rate_limiter", _StubRateLimiter(allowed=True))
    monkeypatch.setattr(auth_routes, "login_slot", lambda: _noop_slot())

    auth_service = _StubAuthService(user_data=None)
    request = _DummyRequest(form_data={"captcha_token": "tok"})
    response = Response()
    form = OAuth2PasswordRequestForm(
        username="user@example.com",
        password="pass",
        scope="",
        client_id=None,
        client_secret=None,
    )

    with pytest.raises(HTTPException) as exc:
        await auth_routes.login(request, response, form, auth_service, cache_service=object())
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_login_rate_limited(monkeypatch):
    monkeypatch.setattr(auth_routes, "account_lockout", _StubLockout(locked=False))
    monkeypatch.setattr(auth_routes, "captcha_verifier", _StubCaptcha(required=False))
    monkeypatch.setattr(auth_routes, "account_rate_limiter", _StubRateLimiter(allowed=False))
    monkeypatch.setattr(auth_routes, "login_slot", lambda: _noop_slot())

    auth_service = _StubAuthService(user_data=None)
    request = _DummyRequest()
    response = Response()
    form = OAuth2PasswordRequestForm(
        username="user@example.com",
        password="pass",
        scope="",
        client_id=None,
        client_secret=None,
    )

    with pytest.raises(HTTPException) as exc:
        await auth_routes.login(request, response, form, auth_service, cache_service=object())
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_login_invalid_credentials(monkeypatch):
    monkeypatch.setattr(auth_routes, "account_lockout", _StubLockout(locked=False))
    monkeypatch.setattr(auth_routes, "captcha_verifier", _StubCaptcha(required=False))
    monkeypatch.setattr(auth_routes, "account_rate_limiter", _StubRateLimiter(allowed=True))
    monkeypatch.setattr(auth_routes, "login_slot", lambda: _noop_slot())

    async def _false_password(*_args, **_kwargs):
        return False

    monkeypatch.setattr(auth_routes, "verify_password_async", _false_password)

    auth_service = _StubAuthService(user_data=None)
    request = _DummyRequest()
    response = Response()
    form = OAuth2PasswordRequestForm(
        username="user@example.com",
        password="pass",
        scope="",
        client_id=None,
        client_secret=None,
    )

    with pytest.raises(HTTPException) as exc:
        await auth_routes.login(request, response, form, auth_service, cache_service=object())
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_login_deactivated_account(monkeypatch):
    monkeypatch.setattr(auth_routes, "account_lockout", _StubLockout(locked=False))
    monkeypatch.setattr(auth_routes, "captcha_verifier", _StubCaptcha(required=False))
    monkeypatch.setattr(auth_routes, "account_rate_limiter", _StubRateLimiter(allowed=True))
    monkeypatch.setattr(auth_routes, "login_slot", lambda: _noop_slot())

    async def _true_password(*_args, **_kwargs):
        return True

    monkeypatch.setattr(auth_routes, "verify_password_async", _true_password)

    user_obj = SimpleNamespace(email="user@example.com", totp_enabled=False)
    user_data = {
        "id": "user",
        "email": "user@example.com",
        "hashed_password": get_password_hash("pass"),
        "account_status": "deactivated",
        "totp_enabled": False,
        "_user_obj": user_obj,
        "_beta_claims": None,
    }
    auth_service = _StubAuthService(user_data=user_data)
    request = _DummyRequest()
    response = Response()
    form = OAuth2PasswordRequestForm(
        username="user@example.com",
        password="pass",
        scope="",
        client_id=None,
        client_secret=None,
    )

    with pytest.raises(HTTPException) as exc:
        await auth_routes.login(request, response, form, auth_service, cache_service=object())
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_login_two_factor_challenge(monkeypatch):
    monkeypatch.setattr(auth_routes, "account_lockout", _StubLockout(locked=False))
    monkeypatch.setattr(auth_routes, "captcha_verifier", _StubCaptcha(required=False))
    monkeypatch.setattr(auth_routes, "account_rate_limiter", _StubRateLimiter(allowed=True))
    monkeypatch.setattr(auth_routes, "login_slot", lambda: _noop_slot())

    async def _true_password(*_args, **_kwargs):
        return True

    monkeypatch.setattr(auth_routes, "verify_password_async", _true_password)

    user_obj = SimpleNamespace(email="user@example.com", totp_enabled=True)
    user_data = {
        "id": "user",
        "email": "user@example.com",
        "hashed_password": get_password_hash("pass"),
        "account_status": None,
        "totp_enabled": True,
        "_user_obj": user_obj,
        "_beta_claims": None,
    }
    auth_service = _StubAuthService(user_data=user_data)
    request = _DummyRequest()
    response = Response()
    form = OAuth2PasswordRequestForm(
        username="user@example.com",
        password="pass",
        scope="",
        client_id=None,
        client_secret=None,
    )

    result = await auth_routes.login(request, response, form, auth_service, cache_service=object())
    assert result.requires_2fa is True


@pytest.mark.asyncio
async def test_login_captcha_valid_success_trims_known_devices(monkeypatch):
    monkeypatch.setattr(auth_routes, "account_lockout", _StubLockout(locked=False))
    monkeypatch.setattr(auth_routes, "captcha_verifier", _StubCaptcha(required=True, valid=True))
    monkeypatch.setattr(auth_routes, "account_rate_limiter", _StubRateLimiter(allowed=True))
    monkeypatch.setattr(auth_routes, "login_slot", lambda: _noop_slot())
    monkeypatch.setattr(
        auth_routes, "_send_new_device_login_notification_sync", lambda **_k: None
    )
    monkeypatch.setenv("SITE_MODE", "prod")

    async def _true_password(*_args, **_kwargs):
        return True

    monkeypatch.setattr(auth_routes, "verify_password_async", _true_password)

    user_obj = SimpleNamespace(email="user@example.com", totp_enabled=False)
    user_data = {
        "id": "user",
        "email": "user@example.com",
        "hashed_password": get_password_hash("pass"),
        "account_status": None,
        "totp_enabled": False,
        "_user_obj": user_obj,
        "_beta_claims": None,
    }
    auth_service = _StubAuthService(user_data=user_data)

    request = _DummyRequest(headers={"user-agent": "agent"}, form_data={"captcha_token": "tok"})
    response = Response()
    form = OAuth2PasswordRequestForm(
        username="user@example.com",
        password="pass",
        scope="",
        client_id=None,
        client_secret=None,
    )

    initial = [f"dev{i}" for i in range(auth_routes.KNOWN_DEVICE_MAX)]
    cache = _StubCache(initial=initial)

    result = await auth_routes.login(request, response, form, auth_service, cache_service=cache)
    assert result.requires_2fa is False
    assert len(cache._store["known_devices:user"]) == auth_routes.KNOWN_DEVICE_MAX


@pytest.mark.asyncio
async def test_login_preview_claims(monkeypatch):
    monkeypatch.setattr(auth_routes, "account_lockout", _StubLockout(locked=False))
    monkeypatch.setattr(auth_routes, "captcha_verifier", _StubCaptcha(required=False))
    monkeypatch.setattr(auth_routes, "account_rate_limiter", _StubRateLimiter(allowed=True))
    monkeypatch.setattr(auth_routes, "login_slot", lambda: _noop_slot())
    monkeypatch.setenv("SITE_MODE", "preview")

    async def _true_password(*_args, **_kwargs):
        return True

    monkeypatch.setattr(auth_routes, "verify_password_async", _true_password)

    user_obj = SimpleNamespace(email="user@example.com", totp_enabled=False)
    user_data = {
        "id": "user",
        "email": "user@example.com",
        "hashed_password": get_password_hash("pass"),
        "account_status": None,
        "totp_enabled": False,
        "_user_obj": user_obj,
        "_beta_claims": None,
    }
    auth_service = _StubAuthService(user_data=user_data)

    request = _DummyRequest()
    response = Response()
    form = OAuth2PasswordRequestForm(
        username="user@example.com",
        password="pass",
        scope="",
        client_id=None,
        client_secret=None,
    )

    result = await auth_routes.login(request, response, form, auth_service, cache_service=object())
    assert result.requires_2fa is False


@pytest.mark.asyncio
async def test_register_guest_conversion_error_and_invite_warning(monkeypatch, db):
    user = SimpleNamespace(
        id="user",
        email="user@example.com",
        first_name="First",
        last_name="Last",
        phone=None,
        zip_code="10001",
        is_active=True,
        timezone="UTC",
        roles=[],
        profile_picture_version=0,
        has_profile_picture=False,
    )
    auth_service = _StubRegisterService(user=user)

    def _convert_boom(*_args, **_kwargs):
        raise RuntimeError("convert")

    monkeypatch.setattr(
        "app.routes.v1.auth.SearchHistoryService.convert_guest_searches_to_user",
        _convert_boom,
    )

    def _consume(self, **_kwargs):
        return False, "not-allowed", None

    monkeypatch.setattr(auth_routes.BetaService, "consume_and_grant", _consume)

    payload = auth_routes.UserCreate(
        email="user@example.com",
        password="Strong123",
        first_name="First",
        last_name="Last",
        zip_code="10001",
        role="student",
        guest_session_id="guest",
        metadata={"invite_code": "INVITE"},
    )
    response = Response()
    result = await auth_routes.register(
        _DummyRequest(), response, payload, auth_service, db, cache_service=_StubCache()
    )

    assert result.email == "user@example.com"


@pytest.mark.asyncio
async def test_register_invite_exception_is_logged(monkeypatch, db):
    user = SimpleNamespace(
        id="user",
        email="user@example.com",
        first_name="First",
        last_name="Last",
        phone=None,
        zip_code="10001",
        is_active=True,
        timezone="UTC",
        roles=[],
        profile_picture_version=0,
        has_profile_picture=False,
    )
    auth_service = _StubRegisterService(user=user)

    def _consume_boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(auth_routes.BetaService, "consume_and_grant", _consume_boom)

    payload = auth_routes.UserCreate(
        email="user@example.com",
        password="Strong123",
        first_name="First",
        last_name="Last",
        zip_code="10001",
        role="student",
        metadata={"invite_code": "INVITE"},
    )
    response = Response()

    result = await auth_routes.register(
        _DummyRequest(), response, payload, auth_service, db, cache_service=_StubCache()
    )
    assert result.email == "user@example.com"


@pytest.mark.asyncio
async def test_register_conflict_and_unexpected_errors(db):
    payload = auth_routes.UserCreate(
        email="user@example.com",
        password="Strong123",
        first_name="First",
        last_name="Last",
        zip_code="10001",
        role="student",
    )
    response = Response()

    conflict_service = _StubRegisterService(exc=ConflictException("dup"))
    with pytest.raises(HTTPException) as exc:
        await auth_routes.register(
            _DummyRequest(), response, payload, conflict_service, db, cache_service=_StubCache()
        )
    assert exc.value.status_code == 409

    error_service = _StubRegisterService(exc=RuntimeError("boom"))
    with pytest.raises(HTTPException) as exc:
        await auth_routes.register(
            _DummyRequest(), response, payload, error_service, db, cache_service=_StubCache()
        )
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_login_with_session_captcha_missing(monkeypatch, db):
    monkeypatch.setattr(auth_routes, "account_lockout", _StubLockout(locked=False))
    monkeypatch.setattr(auth_routes, "captcha_verifier", _StubCaptcha(required=True))
    monkeypatch.setattr(auth_routes, "account_rate_limiter", _StubRateLimiter(allowed=True))
    monkeypatch.setattr(auth_routes, "login_slot", lambda: _noop_slot())

    auth_service = _StubAuthService(user_data=None)
    request = _DummyRequest()
    response = Response()
    login_data = auth_routes.UserLogin(email="user@example.com", password="pass")

    with pytest.raises(HTTPException) as exc:
        await auth_routes.login_with_session(
            request, response, login_data, auth_service, db, cache_service=object()
        )
    assert exc.value.status_code == 428


@pytest.mark.asyncio
async def test_login_with_session_locked_out(monkeypatch, db):
    monkeypatch.setattr(auth_routes, "account_lockout", _StubLockout(locked=True))
    monkeypatch.setattr(auth_routes, "captcha_verifier", _StubCaptcha(required=False))
    monkeypatch.setattr(auth_routes, "account_rate_limiter", _StubRateLimiter(allowed=True))
    monkeypatch.setattr(auth_routes, "login_slot", lambda: _noop_slot())

    auth_service = _StubAuthService(user_data=None)
    request = _DummyRequest()
    response = Response()
    login_data = auth_routes.UserLogin(email="user@example.com", password="pass")

    with pytest.raises(HTTPException) as exc:
        await auth_routes.login_with_session(
            request, response, login_data, auth_service, db, cache_service=object()
        )
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_login_with_session_captcha_failed(monkeypatch, db):
    monkeypatch.setattr(auth_routes, "account_lockout", _StubLockout(locked=False))
    monkeypatch.setattr(auth_routes, "captcha_verifier", _StubCaptcha(required=True, valid=False))
    monkeypatch.setattr(auth_routes, "account_rate_limiter", _StubRateLimiter(allowed=True))
    monkeypatch.setattr(auth_routes, "login_slot", lambda: _noop_slot())

    auth_service = _StubAuthService(user_data=None)
    request = _DummyRequest()
    response = Response()
    login_data = auth_routes.UserLogin(
        email="user@example.com", password="pass", captcha_token="token"
    )

    with pytest.raises(HTTPException) as exc:
        await auth_routes.login_with_session(
            request, response, login_data, auth_service, db, cache_service=object()
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_login_with_session_rate_limited(monkeypatch, db):
    monkeypatch.setattr(auth_routes, "account_lockout", _StubLockout(locked=False))
    monkeypatch.setattr(auth_routes, "captcha_verifier", _StubCaptcha(required=False))
    monkeypatch.setattr(auth_routes, "account_rate_limiter", _StubRateLimiter(allowed=False))
    monkeypatch.setattr(auth_routes, "login_slot", lambda: _noop_slot())

    auth_service = _StubAuthService(user_data=None)
    request = _DummyRequest()
    response = Response()
    login_data = auth_routes.UserLogin(email="user@example.com", password="pass")

    with pytest.raises(HTTPException) as exc:
        await auth_routes.login_with_session(
            request, response, login_data, auth_service, db, cache_service=object()
        )
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_login_with_session_invalid_credentials(monkeypatch, db):
    monkeypatch.setattr(auth_routes, "account_lockout", _StubLockout(locked=False))
    monkeypatch.setattr(auth_routes, "captcha_verifier", _StubCaptcha(required=False))
    monkeypatch.setattr(auth_routes, "account_rate_limiter", _StubRateLimiter(allowed=True))
    monkeypatch.setattr(auth_routes, "login_slot", lambda: _noop_slot())

    async def _false_password(*_args, **_kwargs):
        return False

    monkeypatch.setattr(auth_routes, "verify_password_async", _false_password)

    user_obj = SimpleNamespace(email="user@example.com", totp_enabled=False)
    user_data = {
        "id": "user",
        "email": "user@example.com",
        "hashed_password": get_password_hash("pass"),
        "account_status": None,
        "totp_enabled": False,
        "_user_obj": user_obj,
        "_beta_claims": None,
    }
    auth_service = _StubAuthService(user_data=user_data)
    request = _DummyRequest()
    response = Response()
    login_data = auth_routes.UserLogin(email="user@example.com", password="pass")

    with pytest.raises(HTTPException) as exc:
        await auth_routes.login_with_session(
            request, response, login_data, auth_service, db, cache_service=object()
        )
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_login_with_session_guest_conversion_error(monkeypatch, db):
    monkeypatch.setattr(auth_routes, "account_lockout", _StubLockout(locked=False))
    monkeypatch.setattr(auth_routes, "captcha_verifier", _StubCaptcha(required=True, valid=True))
    monkeypatch.setattr(auth_routes, "account_rate_limiter", _StubRateLimiter(allowed=True))
    monkeypatch.setattr(auth_routes, "login_slot", lambda: _noop_slot())

    async def _true_password(*_args, **_kwargs):
        return True

    monkeypatch.setattr(auth_routes, "verify_password_async", _true_password)

    user_obj = SimpleNamespace(email="user@example.com", totp_enabled=False)
    user_data = {
        "id": "user",
        "email": "user@example.com",
        "hashed_password": get_password_hash("pass"),
        "account_status": None,
        "totp_enabled": False,
        "_user_obj": user_obj,
        "_beta_claims": None,
    }
    auth_service = _StubAuthService(user_data=user_data)

    def _convert_boom(*_args, **_kwargs):
        raise RuntimeError("convert")

    monkeypatch.setattr(
        "app.routes.v1.auth.SearchHistoryService.convert_guest_searches_to_user",
        _convert_boom,
    )

    monkeypatch.setenv("SITE_MODE", "prod")

    request = _DummyRequest()
    response = Response()
    login_data = auth_routes.UserLogin(
        email="user@example.com",
        password="pass",
        guest_session_id="guest",
        captcha_token="token",
    )

    result = await auth_routes.login_with_session(
        request, response, login_data, auth_service, db, cache_service=object()
    )

    assert result.requires_2fa is False


@pytest.mark.asyncio
async def test_login_with_session_guest_conversion_success(monkeypatch, db):
    monkeypatch.setattr(auth_routes, "account_lockout", _StubLockout(locked=False))
    monkeypatch.setattr(auth_routes, "captcha_verifier", _StubCaptcha(required=False))
    monkeypatch.setattr(auth_routes, "account_rate_limiter", _StubRateLimiter(allowed=True))
    monkeypatch.setattr(auth_routes, "login_slot", lambda: _noop_slot())
    monkeypatch.setattr(
        auth_routes, "_send_new_device_login_notification_sync", lambda **_k: None
    )

    async def _true_password(*_args, **_kwargs):
        return True

    monkeypatch.setattr(auth_routes, "verify_password_async", _true_password)

    user_obj = SimpleNamespace(email="user@example.com", totp_enabled=False)
    user_data = {
        "id": "user",
        "email": "user@example.com",
        "hashed_password": get_password_hash("pass"),
        "account_status": None,
        "totp_enabled": False,
        "_user_obj": user_obj,
        "_beta_claims": None,
    }
    auth_service = _StubAuthService(user_data=user_data)

    monkeypatch.setattr(
        "app.routes.v1.auth.SearchHistoryService.convert_guest_searches_to_user",
        lambda *args, **_kwargs: 3,
    )

    request = _DummyRequest()
    response = Response()
    login_data = auth_routes.UserLogin(
        email="user@example.com",
        password="pass",
        guest_session_id="guest",
    )

    result = await auth_routes.login_with_session(
        request, response, login_data, auth_service, db, cache_service=_StubCache()
    )

    assert result.requires_2fa is False


@pytest.mark.asyncio
async def test_login_with_session_two_factor_guest_session(monkeypatch, db):
    monkeypatch.setattr(auth_routes, "account_lockout", _StubLockout(locked=False))
    monkeypatch.setattr(auth_routes, "captcha_verifier", _StubCaptcha(required=False))
    monkeypatch.setattr(auth_routes, "account_rate_limiter", _StubRateLimiter(allowed=True))
    monkeypatch.setattr(auth_routes, "login_slot", lambda: _noop_slot())

    async def _true_password(*_args, **_kwargs):
        return True

    monkeypatch.setattr(auth_routes, "verify_password_async", _true_password)

    def _issue(user_obj, request, extra_claims=None):
        assert extra_claims == {"guest_session_id": "guest"}
        return auth_routes.LoginResponse(requires_2fa=True, temp_token="temp")

    monkeypatch.setattr(auth_routes, "_issue_two_factor_challenge_if_needed", _issue)

    user_obj = SimpleNamespace(email="user@example.com", totp_enabled=True)
    user_data = {
        "id": "user",
        "email": "user@example.com",
        "hashed_password": get_password_hash("pass"),
        "account_status": None,
        "totp_enabled": True,
        "_user_obj": user_obj,
        "_beta_claims": None,
    }
    auth_service = _StubAuthService(user_data=user_data)

    request = _DummyRequest()
    response = Response()
    login_data = auth_routes.UserLogin(
        email="user@example.com",
        password="pass",
        guest_session_id="guest",
    )

    result = await auth_routes.login_with_session(
        request, response, login_data, auth_service, db, cache_service=object()
    )
    assert result.requires_2fa is True


@pytest.mark.asyncio
async def test_login_with_session_deactivated(monkeypatch, db):
    monkeypatch.setattr(auth_routes, "account_lockout", _StubLockout(locked=False))
    monkeypatch.setattr(auth_routes, "captcha_verifier", _StubCaptcha(required=False))
    monkeypatch.setattr(auth_routes, "account_rate_limiter", _StubRateLimiter(allowed=True))
    monkeypatch.setattr(auth_routes, "login_slot", lambda: _noop_slot())

    async def _true_password(*_args, **_kwargs):
        return True

    monkeypatch.setattr(auth_routes, "verify_password_async", _true_password)

    user_obj = SimpleNamespace(email="user@example.com", totp_enabled=False)
    user_data = {
        "id": "user",
        "email": "user@example.com",
        "hashed_password": get_password_hash("pass"),
        "account_status": "deactivated",
        "totp_enabled": False,
        "_user_obj": user_obj,
        "_beta_claims": None,
    }
    auth_service = _StubAuthService(user_data=user_data)

    request = _DummyRequest()
    response = Response()
    login_data = auth_routes.UserLogin(email="user@example.com", password="pass")

    with pytest.raises(HTTPException) as exc:
        await auth_routes.login_with_session(
            request, response, login_data, auth_service, db, cache_service=object()
        )
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_change_password_error_paths(monkeypatch, test_student, db):
    user = test_student

    async def _false_password(*_args, **_kwargs):
        return False

    monkeypatch.setattr(auth_routes, "verify_password_async", _false_password)

    auth_service = _StubAuthService(user_obj=user)
    request = PasswordChangeRequest(current_password="wrongpw", new_password="Strong123")
    with pytest.raises(HTTPException):
        await auth_routes.change_password(
            request,
            _DummyRequest(),
            user.email,
            auth_service,
            db,
        )

    async def _true_password(*_args, **_kwargs):
        return True

    monkeypatch.setattr(auth_routes, "verify_password_async", _true_password)
    weak_request = PasswordChangeRequest(current_password="password", new_password="weakpass")
    with pytest.raises(HTTPException):
        await auth_routes.change_password(
            weak_request,
            _DummyRequest(),
            user.email,
            auth_service,
            db,
        )

    class _Repo:
        def update_password(self, *_args, **_kwargs):
            return False

        def invalidate_all_tokens(self, *_args, **_kwargs):
            return True

    monkeypatch.setattr(
        "app.repositories.RepositoryFactory.create_user_repository",
        lambda _db: _Repo(),
    )
    strong_request = PasswordChangeRequest(current_password="password", new_password="Strong123")
    with pytest.raises(HTTPException):
        await auth_routes.change_password(
            strong_request,
            _DummyRequest(),
            user.email,
            auth_service,
            db,
        )


@pytest.mark.asyncio
async def test_change_password_invalidation_failure_is_non_blocking(monkeypatch, test_student, db):
    user = test_student

    async def _true_password(*_args, **_kwargs):
        return True

    monkeypatch.setattr(auth_routes, "verify_password_async", _true_password)

    class _Repo:
        def update_password(self, *_args, **_kwargs):
            return True

        def invalidate_all_tokens(self, *_args, **_kwargs):
            return False

    monkeypatch.setattr(
        "app.repositories.RepositoryFactory.create_user_repository",
        lambda _db: _Repo(),
    )

    auth_service = _StubAuthService(user_obj=user)
    request = PasswordChangeRequest(current_password="password", new_password="Strong123")

    response = await auth_routes.change_password(
        request,
        _DummyRequest(),
        user.email,
        auth_service,
        db,
    )
    assert response.message == "Password changed successfully"


@pytest.mark.asyncio
async def test_change_password_calls_invalidate_all_tokens(monkeypatch, test_student, db):
    user = test_student
    calls: list[str] = []
    triggers: list[str | None] = []

    async def _true_password(*_args, **_kwargs):
        return True

    monkeypatch.setattr(auth_routes, "verify_password_async", _true_password)

    class _Repo:
        def update_password(self, *_args, **_kwargs):
            return True

        def invalidate_all_tokens(self, user_id: str, **_kwargs):
            calls.append(user_id)
            triggers.append(_kwargs.get("trigger") if _kwargs else None)
            return True

    monkeypatch.setattr(
        "app.repositories.RepositoryFactory.create_user_repository",
        lambda _db: _Repo(),
    )

    auth_service = _StubAuthService(user_obj=user)
    request = PasswordChangeRequest(current_password="password", new_password="Strong123")

    response = await auth_routes.change_password(
        request,
        _DummyRequest(),
        user.email,
        auth_service,
        db,
    )
    assert response.message == "Password changed successfully"
    assert calls == [user.id]
    assert triggers == ["password_change"]


@pytest.mark.asyncio
async def test_change_password_notification_failure(monkeypatch, test_student, db):
    user = test_student

    async def _true_password(*_args, **_kwargs):
        return True

    monkeypatch.setattr(auth_routes, "verify_password_async", _true_password)

    def _notify_boom(**_kwargs):
        raise RuntimeError("notify")

    monkeypatch.setattr(auth_routes, "_send_password_changed_notification_sync", _notify_boom)

    class _Repo:
        def update_password(self, *_args, **_kwargs):
            return True

        def invalidate_all_tokens(self, *_args, **_kwargs):
            return True

    monkeypatch.setattr(
        "app.repositories.RepositoryFactory.create_user_repository",
        lambda _db: _Repo(),
    )

    auth_service = _StubAuthService(user_obj=user)
    request = PasswordChangeRequest(current_password="password", new_password="Strong123")

    response = await auth_routes.change_password(
        request,
        _DummyRequest(),
        user.email,
        auth_service,
        db,
    )
    assert response.message == "Password changed successfully"


@pytest.mark.asyncio
async def test_change_password_audit_failure(monkeypatch, test_student, db):
    user = test_student

    async def _true_password(*_args, **_kwargs):
        return True

    monkeypatch.setattr(auth_routes, "verify_password_async", _true_password)

    def _audit_boom(*_args, **_kwargs):
        raise RuntimeError("audit failed")

    monkeypatch.setattr(auth_routes.AuditService, "log", _audit_boom)

    class _Repo:
        def update_password(self, *_args, **_kwargs):
            return True

        def invalidate_all_tokens(self, *_args, **_kwargs):
            return True

    monkeypatch.setattr(
        "app.repositories.RepositoryFactory.create_user_repository",
        lambda _db: _Repo(),
    )

    auth_service = _StubAuthService(user_obj=user)
    request = PasswordChangeRequest(current_password="password", new_password="Strong123")

    response = await auth_routes.change_password(
        request,
        _DummyRequest(),
        user.email,
        auth_service,
        db,
    )
    assert response.message == "Password changed successfully"


@pytest.mark.asyncio
async def test_read_users_me_cached_fields():
    user = SimpleNamespace(
        id="user",
        email="user@example.com",
        first_name="First",
        last_name="Last",
        phone=None,
        phone_verified=False,
        zip_code=None,
        is_active=True,
        timezone="UTC",
        profile_picture_version=0,
        roles=[],
        _cached_role_names=["student"],
        _cached_permissions={"perm1"},
        _cached_has_profile_picture=True,
        _cached_beta_access=True,
        _cached_beta_role="student",
        _cached_beta_phase="open",
        _cached_beta_invited_by="admin",
    )

    response = await auth_routes.read_users_me(current_user=user, db=None)
    assert response.roles == ["student"]
    assert response.permissions == ["perm1"]
    assert response.beta_access is True


@pytest.mark.asyncio
async def test_read_users_me_fallback_permissions():
    perm = SimpleNamespace(name="perm")
    role = SimpleNamespace(name="student", permissions=[perm])
    user = SimpleNamespace(
        id="user",
        email="user@example.com",
        first_name="First",
        last_name="Last",
        phone=None,
        phone_verified=False,
        zip_code=None,
        is_active=True,
        timezone="UTC",
        profile_picture_version=0,
        has_profile_picture=True,
        roles=[role],
    )

    response = await auth_routes.read_users_me(current_user=user, db=None)
    assert response.roles == ["student"]
    assert response.permissions == ["perm"]
    assert response.has_profile_picture is True


@pytest.mark.asyncio
async def test_update_current_user_not_found(monkeypatch, test_student, db):
    user = test_student

    class _Repo:
        def update_profile(self, *_args, **_kwargs):
            return None

    monkeypatch.setattr(
        "app.repositories.RepositoryFactory.create_user_repository",
        lambda _db: _Repo(),
    )

    auth_service = _StubAuthService(user_obj=user)
    payload = auth_routes.UserUpdate(first_name="New")

    with pytest.raises(HTTPException) as exc:
        await auth_routes.update_current_user(
            _DummyRequest(), payload, user.email, auth_service, db
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_update_current_user_updates_phone_and_zip(monkeypatch, test_student, db):
    user = test_student

    monkeypatch.setattr(
        "app.core.timezone_service.get_timezone_from_zip",
        lambda _zip: "America/New_York",
    )

    auth_service = _StubAuthService(user_obj=user)
    payload = auth_routes.UserUpdate(phone="+15551234567", zip_code="10001")

    response = await auth_routes.update_current_user(
        _DummyRequest(), payload, user.email, auth_service, db
    )
    assert response.phone == "+15551234567"
    assert response.timezone == "America/New_York"


@pytest.mark.asyncio
async def test_update_current_user_unexpected_error(monkeypatch, test_student, db):
    user = test_student

    def _boom(**_kwargs):
        raise RuntimeError("boom")

    auth_service = _StubAuthService(user_obj=user)
    monkeypatch.setattr(auth_service, "get_current_user", _boom)

    payload = auth_routes.UserUpdate(first_name="New")

    with pytest.raises(HTTPException) as exc:
        await auth_routes.update_current_user(
            _DummyRequest(), payload, user.email, auth_service, db
        )
    assert exc.value.status_code == 500


# ── register: welcome email + cache flag ────────────────────────


@pytest.mark.asyncio
async def test_register_sends_welcome_email_and_sets_cache_flag(monkeypatch, db):
    """Registration should fire welcome email and set recently_registered cache flag."""
    user = SimpleNamespace(
        id="u1",
        email="new@example.com",
        first_name="New",
        last_name="User",
        phone=None,
        zip_code="10001",
        is_active=True,
        timezone="UTC",
        roles=[],
        profile_picture_version=0,
        has_profile_picture=False,
    )
    auth_service = _StubRegisterService(user=user)
    cache = _StubCache()

    welcome_calls = []

    def _stub_welcome(self_ns, user_id, role="student"):
        welcome_calls.append({"user_id": user_id, "role": role})

    monkeypatch.setattr(
        "app.services.notification_service.NotificationService.send_welcome_email",
        _stub_welcome,
    )

    payload = auth_routes.UserCreate(
        email="new@example.com",
        password="Strong123",
        first_name="New",
        last_name="User",
        zip_code="10001",
        role="instructor",
    )
    response = Response()
    result = await auth_routes.register(
        _DummyRequest(), response, payload, auth_service, db, cache_service=cache
    )

    assert result.email == "new@example.com"
    assert len(welcome_calls) == 1
    assert welcome_calls[0]["role"] == "instructor"
    assert cache._store.get(f"recently_registered:{user.id}") is True
    assert cache.last_ttl == 300


@pytest.mark.asyncio
async def test_register_welcome_email_failure_does_not_block(monkeypatch, db):
    """If welcome email raises, registration still succeeds."""
    user = SimpleNamespace(
        id="u2",
        email="fail@example.com",
        first_name="Fail",
        last_name="User",
        phone=None,
        zip_code="10001",
        is_active=True,
        timezone="UTC",
        roles=[],
        profile_picture_version=0,
        has_profile_picture=False,
    )
    auth_service = _StubRegisterService(user=user)
    cache = _StubCache()

    def _boom_welcome(self_ns, user_id, role="student"):
        raise RuntimeError("email down")

    monkeypatch.setattr(
        "app.services.notification_service.NotificationService.send_welcome_email",
        _boom_welcome,
    )

    payload = auth_routes.UserCreate(
        email="fail@example.com",
        password="Strong123",
        first_name="Fail",
        last_name="User",
        zip_code="10001",
        role="student",
    )
    response = Response()
    result = await auth_routes.register(
        _DummyRequest(), response, payload, auth_service, db, cache_service=cache
    )

    # Registration still succeeds even though welcome email failed
    assert result.email == "fail@example.com"
    # Cache flag should still be set (separate try-block)
    assert cache._store.get(f"recently_registered:{user.id}") is True


# ── _maybe_send_new_device_login: recently_registered path ──────


@pytest.mark.asyncio
async def test_maybe_send_suppressed_for_recently_registered():
    """When recently_registered flag exists, new-device-login is skipped and device is registered."""
    req = _DummyRequest(headers={"user-agent": "test-agent"})
    cache = _StubCache()
    # Seed the recently_registered flag
    await cache.set("recently_registered:u1", True)

    await auth_routes._maybe_send_new_device_login_notification(
        user_id="u1", request=req, cache_service=cache
    )

    # The recently_registered flag should be deleted
    assert cache._store.get("recently_registered:u1") is None
    # The device should be registered as known
    fingerprint = auth_routes._device_fingerprint("127.0.0.1", "test-agent")
    assert cache._store.get("known_devices:u1") == [fingerprint]


@pytest.mark.asyncio
async def test_maybe_send_recently_registered_registers_device_correctly():
    """recently_registered path should register device with correct TTL."""
    req = _DummyRequest(headers={"user-agent": "my-browser"}, client_host="10.0.0.1")
    cache = _StubCache()
    await cache.set("recently_registered:u2", True)

    await auth_routes._maybe_send_new_device_login_notification(
        user_id="u2", request=req, cache_service=cache
    )

    fingerprint = auth_routes._device_fingerprint("10.0.0.1", "my-browser")
    assert cache._store["known_devices:u2"] == [fingerprint]
    assert cache.last_ttl == auth_routes.KNOWN_DEVICE_TTL_SECONDS
    # Flag cleaned up
    assert "recently_registered:u2" not in cache._store


@pytest.mark.asyncio
async def test_login_sets_access_and_refresh_cookies(monkeypatch):
    monkeypatch.setattr(auth_routes, "account_lockout", _StubLockout(locked=False))
    monkeypatch.setattr(auth_routes, "captcha_verifier", _StubCaptcha(required=False))
    monkeypatch.setattr(auth_routes, "account_rate_limiter", _StubRateLimiter(allowed=True))
    monkeypatch.setattr(auth_routes, "login_slot", lambda: _noop_slot())

    async def _true_password(*_args, **_kwargs):
        return True

    monkeypatch.setattr(auth_routes, "verify_password_async", _true_password)

    user_obj = SimpleNamespace(email="user@example.com", totp_enabled=False)
    user_data = {
        "id": "user",
        "email": "user@example.com",
        "hashed_password": get_password_hash("pass"),
        "account_status": None,
        "totp_enabled": False,
        "_user_obj": user_obj,
        "_beta_claims": None,
    }
    auth_service = _StubAuthService(user_data=user_data)
    request = _DummyRequest()
    response = Response()
    form = OAuth2PasswordRequestForm(
        username="user@example.com",
        password="pass",
        scope="",
        client_id=None,
        client_secret=None,
    )

    result = await auth_routes.login(request, response, form, auth_service, cache_service=object())
    assert result.requires_2fa is False

    set_cookie_headers = response.headers.getlist("set-cookie")
    assert any("Path=/api/v1/auth/refresh" in header for header in set_cookie_headers)
    assert any("Path=/" in header and "sid" in header for header in set_cookie_headers)


@pytest.mark.asyncio
async def test_login_with_session_sets_access_and_refresh_cookies(monkeypatch, db):
    monkeypatch.setattr(auth_routes, "account_lockout", _StubLockout(locked=False))
    monkeypatch.setattr(auth_routes, "captcha_verifier", _StubCaptcha(required=False))
    monkeypatch.setattr(auth_routes, "account_rate_limiter", _StubRateLimiter(allowed=True))
    monkeypatch.setattr(auth_routes, "login_slot", lambda: _noop_slot())

    async def _true_password(*_args, **_kwargs):
        return True

    monkeypatch.setattr(auth_routes, "verify_password_async", _true_password)

    user_obj = SimpleNamespace(email="user@example.com", totp_enabled=False)
    user_data = {
        "id": "user",
        "email": "user@example.com",
        "hashed_password": get_password_hash("pass"),
        "account_status": None,
        "totp_enabled": False,
        "_user_obj": user_obj,
        "_beta_claims": None,
    }
    auth_service = _StubAuthService(user_data=user_data)
    request = _DummyRequest()
    response = Response()
    login_data = auth_routes.UserLogin(email="user@example.com", password="pass")

    result = await auth_routes.login_with_session(
        request,
        response,
        login_data,
        auth_service,
        db,
        cache_service=object(),
    )
    assert result.requires_2fa is False

    set_cookie_headers = response.headers.getlist("set-cookie")
    assert any("Path=/api/v1/auth/refresh" in header for header in set_cookie_headers)
    assert any("Path=/" in header and "sid" in header for header in set_cookie_headers)


@pytest.mark.asyncio
async def test_refresh_session_token_rotates_tokens(monkeypatch):
    now_ts = int(datetime.now(timezone.utc).timestamp())
    refresh_payload = {
        "sub": "01HREFRESHUSERID00000000000",
        "email": "user@example.com",
        "jti": "01HOLDREFRESHTOKENJTI000000",
        "iat": now_ts,
        "exp": now_ts + 3600,
        "typ": "refresh",
    }
    blacklist_calls: dict[str, object] = {}

    class _Blacklist:
        async def claim_and_revoke(self, jti: str, exp: int) -> bool:
            blacklist_calls["jti"] = jti
            blacklist_calls["exp"] = exp
            return True

    class _Repo:
        def get_by_id(self, user_id: str):
            return SimpleNamespace(
                id=user_id,
                email="user@example.com",
                is_active=True,
                tokens_valid_after=None,
            )

    monkeypatch.setattr(auth_routes, "TokenBlacklistService", _Blacklist)
    monkeypatch.setattr(auth_routes, "decode_access_token", lambda _token: refresh_payload)
    monkeypatch.setattr(
        "app.repositories.RepositoryFactory.create_user_repository",
        lambda _db: _Repo(),
    )
    monkeypatch.setattr(auth_routes, "create_access_token", lambda *a, **k: "new-access-token")
    monkeypatch.setattr(auth_routes, "create_refresh_token", lambda *a, **k: "new-refresh-token")

    request = _DummyRequest(
        cookies={auth_routes.refresh_cookie_base_name(auth_routes.settings.site_mode): "old"}
    )
    response = Response()

    result = await auth_routes.refresh_session_token(request, response, db=object())
    assert result.message == "Session refreshed"

    set_cookie_headers = response.headers.getlist("set-cookie")
    assert any("new-access-token" in header for header in set_cookie_headers)
    assert any("new-refresh-token" in header for header in set_cookie_headers)
    assert any("Path=/api/v1/auth/refresh" in header for header in set_cookie_headers)
    assert blacklist_calls["jti"] == refresh_payload["jti"]
    assert blacklist_calls["exp"] == refresh_payload["exp"]


@pytest.mark.asyncio
async def test_refresh_session_token_rejects_missing_cookie():
    request = _DummyRequest(cookies={})
    response = Response()

    with pytest.raises(HTTPException) as exc:
        await auth_routes.refresh_session_token(request, response, db=object())
    assert exc.value.status_code == 401
    assert exc.value.detail == "Not authenticated"


@pytest.mark.asyncio
async def test_refresh_session_token_rejects_wrong_token_type(monkeypatch):
    wrong_type_payload = {"sub": "01HUSER000000000000000000", "jti": "jti", "typ": "access"}
    monkeypatch.setattr(auth_routes, "decode_access_token", lambda _token: wrong_type_payload)

    request = _DummyRequest(
        cookies={auth_routes.refresh_cookie_base_name(auth_routes.settings.site_mode): "old"}
    )
    response = Response()

    with pytest.raises(HTTPException) as exc:
        await auth_routes.refresh_session_token(request, response, db=object())
    assert exc.value.status_code == 401
    assert exc.value.detail == "Could not validate credentials"


@pytest.mark.asyncio
async def test_refresh_session_token_rejects_revoked_token(monkeypatch):
    now_ts = int(datetime.now(timezone.utc).timestamp())
    refresh_payload = {
        "sub": "01HUSER000000000000000000",
        "email": "user@example.com",
        "jti": "01HOLDREFRESHTOKENJTI000000",
        "iat": now_ts,
        "exp": now_ts + 3600,
        "typ": "refresh",
    }

    class _Blacklist:
        async def claim_and_revoke(self, _jti: str, _exp: int) -> bool:
            return False  # already claimed — replay rejected

    class _Repo:
        def get_by_id(self, user_id: str):
            return SimpleNamespace(
                id=user_id,
                email="user@example.com",
                is_active=True,
                tokens_valid_after=None,
            )

    monkeypatch.setattr(auth_routes, "TokenBlacklistService", _Blacklist)
    monkeypatch.setattr(auth_routes, "decode_access_token", lambda _token: refresh_payload)
    monkeypatch.setattr(
        "app.repositories.RepositoryFactory.create_user_repository",
        lambda _db: _Repo(),
    )

    request = _DummyRequest(
        cookies={auth_routes.refresh_cookie_base_name(auth_routes.settings.site_mode): "old"}
    )
    response = Response()

    with pytest.raises(HTTPException) as exc:
        await auth_routes.refresh_session_token(request, response, db=object())
    assert exc.value.status_code == 401
    assert exc.value.detail == "Token has been revoked"


@pytest.mark.asyncio
async def test_refresh_session_token_rejects_invalidated_token(monkeypatch):
    now_ts = int(datetime.now(timezone.utc).timestamp())
    refresh_payload = {
        "sub": "01HUSER000000000000000000",
        "email": "user@example.com",
        "jti": "01HOLDREFRESHTOKENJTI000000",
        "iat": now_ts,
        "exp": now_ts + 3600,
        "typ": "refresh",
    }

    class _Blacklist:
        async def claim_and_revoke(self, _jti: str, _exp: int) -> bool:
            return True  # never reached — tokens_valid_after rejects first

    class _Repo:
        def get_by_id(self, user_id: str):
            return SimpleNamespace(
                id=user_id,
                email="user@example.com",
                is_active=True,
                tokens_valid_after=datetime.now(timezone.utc) + timedelta(minutes=5),
            )

    monkeypatch.setattr(auth_routes, "TokenBlacklistService", _Blacklist)
    monkeypatch.setattr(auth_routes, "decode_access_token", lambda _token: refresh_payload)
    monkeypatch.setattr(
        "app.repositories.RepositoryFactory.create_user_repository",
        lambda _db: _Repo(),
    )

    request = _DummyRequest(
        cookies={auth_routes.refresh_cookie_base_name(auth_routes.settings.site_mode): "old"}
    )
    response = Response()

    with pytest.raises(HTTPException) as exc:
        await auth_routes.refresh_session_token(request, response, db=object())
    assert exc.value.status_code == 401
    assert exc.value.detail == "Token has been invalidated"


@pytest.mark.asyncio
async def test_refresh_session_token_rotation_replay_rejected(monkeypatch):
    """M2: Full rotation replay — old refresh token rejected after successful refresh."""
    now_ts = int(datetime.now(timezone.utc).timestamp())
    refresh_payload = {
        "sub": "01HREPLAYUSERID0000000000",
        "email": "replay@example.com",
        "jti": "01HFIRSTJTI00000000000000",
        "iat": now_ts,
        "exp": now_ts + 3600,
        "typ": "refresh",
    }

    claimed_jtis: list[str] = []

    class _Blacklist:
        """Simulates a real blacklist: first claim succeeds, replay fails."""

        def __init__(self):
            self._claimed: set[str] = set()

        async def claim_and_revoke(self, jti: str, _exp: int) -> bool:
            claimed_jtis.append(jti)
            if jti in self._claimed:
                return False
            self._claimed.add(jti)
            return True

    class _Repo:
        def get_by_id(self, user_id: str):
            return SimpleNamespace(
                id=user_id,
                email="replay@example.com",
                is_active=True,
                tokens_valid_after=None,
            )

    blacklist_instance = _Blacklist()
    monkeypatch.setattr(auth_routes, "TokenBlacklistService", lambda: blacklist_instance)
    monkeypatch.setattr(auth_routes, "decode_access_token", lambda _token: refresh_payload)
    monkeypatch.setattr(
        "app.repositories.RepositoryFactory.create_user_repository",
        lambda _db: _Repo(),
    )
    monkeypatch.setattr(auth_routes, "create_access_token", lambda *a, **k: "new-access")
    monkeypatch.setattr(auth_routes, "create_refresh_token", lambda *a, **k: "new-refresh")

    cookie_name = auth_routes.refresh_cookie_base_name(auth_routes.settings.site_mode)

    # First refresh succeeds
    request1 = _DummyRequest(cookies={cookie_name: "old-refresh-token"})
    response1 = Response()
    result1 = await auth_routes.refresh_session_token(request1, response1, db=object())
    assert result1.message == "Session refreshed"

    # Replay with same JTI is rejected
    request2 = _DummyRequest(cookies={cookie_name: "old-refresh-token"})
    response2 = Response()
    with pytest.raises(HTTPException) as exc:
        await auth_routes.refresh_session_token(request2, response2, db=object())
    assert exc.value.status_code == 401
    assert exc.value.detail == "Token has been revoked"

    assert len(claimed_jtis) == 2
    assert claimed_jtis[0] == claimed_jtis[1] == "01HFIRSTJTI00000000000000"


@pytest.mark.asyncio
async def test_refresh_session_token_rejects_inactive_user(monkeypatch):
    """M3: Refresh rejected when user.is_active is False."""
    now_ts = int(datetime.now(timezone.utc).timestamp())
    refresh_payload = {
        "sub": "01HINACTIVEUSER00000000000",
        "email": "inactive@example.com",
        "jti": "01HINACTIVEJTI000000000000",
        "iat": now_ts,
        "exp": now_ts + 3600,
        "typ": "refresh",
    }

    class _Repo:
        def get_by_id(self, user_id: str):
            return SimpleNamespace(
                id=user_id,
                email="inactive@example.com",
                is_active=False,
                tokens_valid_after=None,
            )

    monkeypatch.setattr(auth_routes, "decode_access_token", lambda _token: refresh_payload)
    monkeypatch.setattr(
        "app.repositories.RepositoryFactory.create_user_repository",
        lambda _db: _Repo(),
    )

    cookie_name = auth_routes.refresh_cookie_base_name(auth_routes.settings.site_mode)
    request = _DummyRequest(cookies={cookie_name: "old"})
    response = Response()

    with pytest.raises(HTTPException) as exc:
        await auth_routes.refresh_session_token(request, response, db=object())
    assert exc.value.status_code == 401
    assert exc.value.detail == "Could not validate credentials"


@pytest.mark.asyncio
async def test_refresh_session_token_rejects_expired_token(monkeypatch):
    """L3: Refresh rejected when token has expired."""

    def _decode_expired(_token: str):
        raise Exception("Signature has expired")

    monkeypatch.setattr(auth_routes, "decode_access_token", _decode_expired)

    cookie_name = auth_routes.refresh_cookie_base_name(auth_routes.settings.site_mode)
    request = _DummyRequest(cookies={cookie_name: "expired-token"})
    response = Response()

    with pytest.raises(HTTPException) as exc:
        await auth_routes.refresh_session_token(request, response, db=object())
    assert exc.value.status_code == 401
    assert exc.value.detail == "Could not validate credentials"
