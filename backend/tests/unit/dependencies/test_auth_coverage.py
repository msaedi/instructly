from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from fastapi import HTTPException
import pytest
from starlette.requests import Request

import app.api.dependencies.auth as auth_module
from app.models.user import User


def _make_request(path="/api/v1/test", headers=None, host="api.preview.example.com") -> Request:
    raw_headers = []
    for key, value in (headers or {}).items():
        raw_headers.append((key.encode(), value.encode()))
    scope = {
        "type": "http",
        "path": path,
        "headers": raw_headers,
        "query_string": b"",
        "client": ("127.0.0.1", 123),
        "server": (host, 443),
        "scheme": "https",
    }
    return Request(scope)


def _make_user(email="staff@example.com", is_staff=True):
    user = User(
        email=email,
        hashed_password="hash",
        first_name="Staff",
        last_name="User",
        zip_code="10001",
        is_active=True,
        account_status="active",
        totp_enabled=False,
        phone_verified=False,
    )
    user.is_staff = is_staff
    return user


def test_from_preview_origin_matches_frontend_and_api(monkeypatch):
    monkeypatch.setattr(auth_module.settings, "preview_frontend_domain", "preview.example.com")
    monkeypatch.setattr(auth_module.settings, "preview_api_domain", "api.preview.example.com")

    request = _make_request(
        headers={
            "origin": "https://preview.example.com",
            "x-forwarded-host": "api.preview.example.com",
        }
    )

    assert auth_module._from_preview_origin(request) is True


def test_preview_bypass_staff(monkeypatch):
    monkeypatch.setenv("PREVIEW_BYPASS_ENABLED", "true")
    monkeypatch.setenv("SITE_MODE", "preview")
    monkeypatch.setattr(auth_module.settings, "preview_frontend_domain", "preview.example.com")
    monkeypatch.setattr(auth_module.settings, "preview_api_domain", "api.preview.example.com")

    request = _make_request(
        headers={
            "origin": "https://preview.example.com",
            "x-forwarded-host": "api.preview.example.com",
        }
    )
    user = _make_user(is_staff=True)

    assert auth_module._preview_bypass(request, user) is True


def test_preview_bypass_disabled(monkeypatch):
    monkeypatch.setenv("PREVIEW_BYPASS_ENABLED", "false")
    monkeypatch.setenv("SITE_MODE", "preview")
    request = _make_request()

    assert auth_module._preview_bypass(request, _make_user(is_staff=True)) is False


def test_preview_bypass_no_staff_no_header_returns_false(monkeypatch):
    monkeypatch.setenv("PREVIEW_BYPASS_ENABLED", "true")
    monkeypatch.setenv("SITE_MODE", "preview")
    monkeypatch.setattr(auth_module.settings, "preview_frontend_domain", "preview.example.com")
    monkeypatch.setattr(auth_module.settings, "preview_api_domain", "api.preview.example.com")

    request = _make_request(
        headers={
            "origin": "https://preview.example.com",
            "x-forwarded-host": "api.preview.example.com",
        }
    )
    user = _make_user(is_staff=False)

    assert auth_module._preview_bypass(request, user) is False


def test_preview_bypass_non_preview_site(monkeypatch):
    monkeypatch.setenv("PREVIEW_BYPASS_ENABLED", "true")
    monkeypatch.setenv("SITE_MODE", "prod")
    request = _make_request()

    assert auth_module._preview_bypass(request, _make_user(is_staff=True)) is False


def test_preview_bypass_requires_preview_origin(monkeypatch):
    monkeypatch.setenv("PREVIEW_BYPASS_ENABLED", "true")
    monkeypatch.setenv("SITE_MODE", "preview")
    monkeypatch.setattr(auth_module.settings, "preview_frontend_domain", "preview.example.com")
    monkeypatch.setattr(auth_module.settings, "preview_api_domain", "api.preview.example.com")

    request = _make_request(headers={"origin": "https://example.com"})

    assert auth_module._preview_bypass(request, _make_user(is_staff=True)) is False


def test_preview_bypass_blocks_webhooks(monkeypatch):
    monkeypatch.setenv("PREVIEW_BYPASS_ENABLED", "true")
    monkeypatch.setenv("SITE_MODE", "preview")
    monkeypatch.setattr(auth_module.settings, "preview_frontend_domain", "preview.example.com")
    monkeypatch.setattr(auth_module.settings, "preview_api_domain", "api.preview.example.com")

    request = _make_request(
        path="/api/v1/webhook/test",
        headers={
            "origin": "https://preview.example.com",
            "x-forwarded-host": "api.preview.example.com",
        },
    )

    assert auth_module._preview_bypass(request, _make_user(is_staff=True)) is False


def test_preview_bypass_handles_webhook_parse_error(monkeypatch):
    monkeypatch.setenv("PREVIEW_BYPASS_ENABLED", "true")
    monkeypatch.setenv("SITE_MODE", "preview")
    monkeypatch.setattr(auth_module, "_from_preview_origin", lambda _req: True)

    class BadUrl:
        @property
        def path(self):
            raise RuntimeError("boom")

    request = SimpleNamespace(headers={}, url=BadUrl(), client=None)

    assert auth_module._preview_bypass(request, _make_user(is_staff=False)) is False


def test_preview_bypass_logs_ignore_errors(monkeypatch):
    monkeypatch.setenv("PREVIEW_BYPASS_ENABLED", "true")
    monkeypatch.setenv("SITE_MODE", "preview")
    monkeypatch.setattr(auth_module.settings, "preview_frontend_domain", "preview.example.com")
    monkeypatch.setattr(auth_module.settings, "preview_api_domain", "api.preview.example.com")
    monkeypatch.setattr(auth_module.prometheus_metrics, "inc_preview_bypass", Mock(side_effect=RuntimeError("boom")))

    request = _make_request(
        headers={
            "origin": "https://preview.example.com",
            "x-forwarded-host": "api.preview.example.com",
        },
    )

    assert auth_module._preview_bypass(request, _make_user(is_staff=True)) is True


def test_preview_bypass_header_token(monkeypatch):
    monkeypatch.setenv("PREVIEW_BYPASS_ENABLED", "true")
    monkeypatch.setenv("SITE_MODE", "preview")
    monkeypatch.setattr(auth_module.settings, "allow_preview_header", True, raising=False)
    monkeypatch.setattr(auth_module.settings, "staff_preview_token", "token", raising=False)
    monkeypatch.setattr(auth_module.settings, "preview_frontend_domain", "preview.example.com")
    monkeypatch.setattr(auth_module.settings, "preview_api_domain", "api.preview.example.com")

    request = _make_request(
        headers={
            "origin": "https://preview.example.com",
            "x-forwarded-host": "api.preview.example.com",
            "x-staff-preview-token": "token",
        }
    )
    user = _make_user(is_staff=False)

    assert auth_module._preview_bypass(request, user) is True


def test_preview_bypass_header_token_logs_ignore_errors(monkeypatch):
    monkeypatch.setenv("PREVIEW_BYPASS_ENABLED", "true")
    monkeypatch.setenv("SITE_MODE", "preview")
    monkeypatch.setattr(auth_module.settings, "allow_preview_header", True, raising=False)
    monkeypatch.setattr(auth_module.settings, "staff_preview_token", "token", raising=False)
    monkeypatch.setattr(auth_module.settings, "preview_frontend_domain", "preview.example.com")
    monkeypatch.setattr(auth_module.settings, "preview_api_domain", "api.preview.example.com")
    monkeypatch.setattr(auth_module.prometheus_metrics, "inc_preview_bypass", Mock(side_effect=RuntimeError("boom")))

    request = _make_request(
        headers={
            "origin": "https://preview.example.com",
            "x-forwarded-host": "api.preview.example.com",
            "x-staff-preview-token": "token",
        }
    )
    user = _make_user(is_staff=False)

    assert auth_module._preview_bypass(request, user) is True

def test_testing_bypass_honors_enforce_header(monkeypatch):
    monkeypatch.setattr(auth_module.settings, "is_testing", True, raising=False)
    request = _make_request(headers={"x-enforce-beta-checks": "1"})

    assert auth_module._testing_bypass(request) is False


def test_testing_bypass_defaults_to_settings(monkeypatch):
    monkeypatch.setattr(auth_module.settings, "is_testing", True, raising=False)
    request = _make_request()

    assert auth_module._testing_bypass(request) is True


def test_testing_bypass_handles_header_error(monkeypatch):
    monkeypatch.setattr(auth_module.settings, "is_testing", True, raising=False)

    class BadHeaders:
        def get(self, _key):
            raise RuntimeError("boom")

    request = _make_request()
    request._headers = BadHeaders()  # type: ignore[attr-defined]

    assert auth_module._testing_bypass(request) is True


@pytest.mark.asyncio
async def test_get_current_user_returns_state_user(monkeypatch):
    request = _make_request()
    user = _make_user(is_staff=False)
    request.state.current_user = user

    result = await auth_module.get_current_user(request, "ignored", db=Mock())

    assert result is user


@pytest.mark.asyncio
async def test_get_current_user_legacy_invalid_db():
    with pytest.raises(HTTPException) as exc:
        await auth_module.get_current_user("user@example.com", object(), object())

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_get_current_user_legacy_success(monkeypatch):
    user = _make_user(is_staff=False)

    class DummyUserRepo:
        def __init__(self, db):
            self.db = db

        def get_by_email(self, email):
            return user

    db = Mock()
    db.query.return_value = Mock()

    monkeypatch.setattr("app.repositories.user_repository.UserRepository", DummyUserRepo)

    result = await auth_module.get_current_user("user@example.com", db, db)

    assert result is user


@pytest.mark.asyncio
async def test_get_current_user_legacy_not_found(monkeypatch):
    class DummyUserRepo:
        def __init__(self, db):
            self.db = db

        def get_by_email(self, email):
            return None

    db = Mock()
    db.query.return_value = Mock()

    monkeypatch.setattr("app.repositories.user_repository.UserRepository", DummyUserRepo)

    with pytest.raises(HTTPException) as exc:
        await auth_module.get_current_user("user@example.com", db, db)

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_current_user_production_not_found(monkeypatch):
    monkeypatch.setattr(auth_module.settings, "is_testing", False, raising=False)
    monkeypatch.setattr(auth_module, "lookup_user_nonblocking", AsyncMock(return_value=None))

    request = _make_request()

    with pytest.raises(HTTPException) as exc:
        await auth_module.get_current_user(request, "missing@example.com", db=Mock())

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_current_user_production_success(monkeypatch):
    monkeypatch.setattr(auth_module.settings, "is_testing", False, raising=False)
    monkeypatch.setattr(auth_module, "lookup_user_nonblocking", AsyncMock(return_value={"id": "u2"}))
    monkeypatch.setattr(auth_module, "create_transient_user", lambda data: SimpleNamespace(id=data["id"]))

    result = await auth_module.get_current_user(_make_request(), "user@example.com", db=Mock())

    assert result.id == "u2"


@pytest.mark.asyncio
async def test_get_current_user_testing_not_found(monkeypatch):
    monkeypatch.setattr(auth_module.settings, "is_testing", True, raising=False)

    class DummyUserRepo:
        def __init__(self, db):
            self.db = db

        def get_by_email(self, email):
            return None

    monkeypatch.setattr("app.repositories.user_repository.UserRepository", DummyUserRepo)

    with pytest.raises(HTTPException) as exc:
        await auth_module.get_current_user(_make_request(), "missing@example.com", db=Mock())

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_current_user_preview_impersonation(monkeypatch):
    monkeypatch.setattr(auth_module.settings, "is_testing", True, raising=False)

    request = _make_request(headers={"x-impersonate-user-id": "imp-123"})
    user = _make_user(is_staff=True)

    class DummyUserRepo:
        def __init__(self, db):
            self.db = db

        def get_by_email(self, email):
            return user

    monkeypatch.setattr(auth_module, "_preview_bypass", lambda *args, **kwargs: True)
    monkeypatch.setattr("app.repositories.user_repository.UserRepository", DummyUserRepo)
    monkeypatch.setattr(auth_module, "lookup_user_by_id_nonblocking", AsyncMock(return_value={"id": "imp-123"}))
    monkeypatch.setattr(auth_module, "create_transient_user", lambda data: SimpleNamespace(id=data["id"]))

    result = await auth_module.get_current_user(request, "staff@example.com", db=Mock())

    assert result.id == "imp-123"


@pytest.mark.asyncio
async def test_get_current_user_preview_impersonation_no_header(monkeypatch):
    monkeypatch.setattr(auth_module.settings, "is_testing", True, raising=False)
    user = _make_user(is_staff=True)

    class DummyUserRepo:
        def __init__(self, db):
            self.db = db

        def get_by_email(self, email):
            return user

    monkeypatch.setattr("app.repositories.user_repository.UserRepository", DummyUserRepo)
    monkeypatch.setattr(auth_module, "_preview_bypass", lambda *args, **kwargs: True)

    result = await auth_module.get_current_user(_make_request(), "staff@example.com", db=Mock())

    assert result is user


@pytest.mark.asyncio
async def test_get_current_user_preview_impersonation_missing_data(monkeypatch):
    monkeypatch.setattr(auth_module.settings, "is_testing", True, raising=False)
    user = _make_user(is_staff=True)

    class DummyUserRepo:
        def __init__(self, db):
            self.db = db

        def get_by_email(self, email):
            return user

    monkeypatch.setattr("app.repositories.user_repository.UserRepository", DummyUserRepo)
    monkeypatch.setattr(auth_module, "_preview_bypass", lambda *args, **kwargs: True)
    monkeypatch.setattr(auth_module, "lookup_user_by_id_nonblocking", AsyncMock(return_value=None))

    request = _make_request(headers={"x-impersonate-user-id": "imp-123"})
    result = await auth_module.get_current_user(request, "staff@example.com", db=Mock())

    assert result is user


@pytest.mark.asyncio
async def test_get_current_user_preview_impersonation_handles_error(monkeypatch):
    monkeypatch.setattr(auth_module.settings, "is_testing", True, raising=False)
    user = _make_user(is_staff=True)

    class DummyUserRepo:
        def __init__(self, db):
            self.db = db

        def get_by_email(self, email):
            return user

    monkeypatch.setattr("app.repositories.user_repository.UserRepository", DummyUserRepo)
    monkeypatch.setattr(auth_module, "_preview_bypass", lambda *args, **kwargs: True)
    monkeypatch.setattr(auth_module, "lookup_user_by_id_nonblocking", AsyncMock(side_effect=RuntimeError("boom")))

    result = await auth_module.get_current_user(_make_request(), "staff@example.com", db=Mock())

    assert result is user


@pytest.mark.asyncio
async def test_get_current_active_user_optional_prefers_state_user(monkeypatch):
    request = _make_request()
    user = _make_user(is_staff=False)
    request.state.current_user = user

    result = await auth_module.get_current_active_user_optional(request, None, db=Mock())

    assert result is user


@pytest.mark.asyncio
async def test_get_current_active_user_optional_production_lookup(monkeypatch):
    monkeypatch.setattr(auth_module.settings, "is_testing", False, raising=False)
    monkeypatch.setattr(auth_module, "lookup_user_nonblocking", AsyncMock(return_value={"id": "u1", "is_active": True}))
    monkeypatch.setattr(auth_module, "create_transient_user", lambda data: SimpleNamespace(id=data["id"]))

    request = _make_request()
    result = await auth_module.get_current_active_user_optional(request, "user@example.com", db=Mock())

    assert result.id == "u1"


@pytest.mark.asyncio
async def test_get_current_active_user_optional_no_email():
    request = _make_request()
    assert await auth_module.get_current_active_user_optional(request, None, db=Mock()) is None


@pytest.mark.asyncio
async def test_get_current_active_user_optional_state_inactive():
    request = _make_request()
    inactive = _make_user(is_staff=False)
    inactive.is_active = False
    request.state.current_user = inactive

    assert await auth_module.get_current_active_user_optional(request, None, db=Mock()) is None


@pytest.mark.asyncio
async def test_get_current_active_user_optional_inactive_user(monkeypatch):
    monkeypatch.setattr(auth_module.settings, "is_testing", True, raising=False)

    inactive = _make_user(is_staff=False)
    inactive.is_active = False

    class DummyUserRepo:
        def __init__(self, db):
            self.db = db

        def get_by_email(self, email):
            return inactive

    monkeypatch.setattr("app.repositories.user_repository.UserRepository", DummyUserRepo)

    result = await auth_module.get_current_active_user_optional(_make_request(), "user@example.com", db=Mock())

    assert result is None


@pytest.mark.asyncio
async def test_get_current_active_user_optional_testing_active_user(monkeypatch):
    monkeypatch.setattr(auth_module.settings, "is_testing", True, raising=False)

    active = _make_user(is_staff=False)

    class DummyUserRepo:
        def __init__(self, db):
            self.db = db

        def get_by_email(self, email):
            return active

    monkeypatch.setattr("app.repositories.user_repository.UserRepository", DummyUserRepo)

    result = await auth_module.get_current_active_user_optional(_make_request(), "user@example.com", db=Mock())

    assert result is active


@pytest.mark.asyncio
async def test_get_current_active_user_optional_production_inactive(monkeypatch):
    monkeypatch.setattr(auth_module.settings, "is_testing", False, raising=False)
    monkeypatch.setattr(auth_module, "lookup_user_nonblocking", AsyncMock(return_value={"id": "u3", "is_active": False}))

    result = await auth_module.get_current_active_user_optional(_make_request(), "user@example.com", db=Mock())

    assert result is None


@pytest.mark.asyncio
async def test_get_current_active_user_rejects_inactive():
    user = _make_user(is_staff=False)
    user.is_active = False
    with pytest.raises(HTTPException) as exc:
        await auth_module.get_current_active_user(user)

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_get_current_active_user_success():
    user = SimpleNamespace(is_active=True)
    result = await auth_module.get_current_active_user(user)
    assert result is user


@pytest.mark.asyncio
async def test_get_current_instructor_rejects_non_instructor():
    user = SimpleNamespace(is_instructor=False)
    with pytest.raises(HTTPException) as exc:
        await auth_module.get_current_instructor(user)

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_get_current_instructor_success():
    user = SimpleNamespace(is_instructor=True)
    result = await auth_module.get_current_instructor(user)
    assert result is user


@pytest.mark.asyncio
async def test_get_current_student_rejects_non_student():
    user = SimpleNamespace(is_student=False)
    with pytest.raises(HTTPException) as exc:
        await auth_module.get_current_student(user)

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_get_current_student_success():
    user = SimpleNamespace(is_student=True)
    result = await auth_module.get_current_student(user)
    assert result is user


@pytest.mark.asyncio
async def test_require_admin_rejects_non_admin():
    user = SimpleNamespace(is_admin=False)
    with pytest.raises(HTTPException) as exc:
        await auth_module.require_admin(user)

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_admin_success():
    user = SimpleNamespace(is_admin=True)
    result = await auth_module.require_admin(user)
    assert result is user

@pytest.mark.asyncio
async def test_require_beta_access_preview_bypass(monkeypatch):
    verify = auth_module.require_beta_access()
    user = _make_user(is_staff=False)

    monkeypatch.setenv("SITE_MODE", "prod")
    monkeypatch.setattr(auth_module, "_preview_bypass", lambda *args, **kwargs: True)

    result = await verify(_make_request(), current_user=user, db=Mock())

    assert result is user


@pytest.mark.asyncio
async def test_require_beta_access_site_mode_preview(monkeypatch):
    verify = auth_module.require_beta_access()
    user = _make_user(is_staff=False)

    monkeypatch.setenv("SITE_MODE", "preview")

    result = await verify(_make_request(), current_user=user, db=Mock())
    assert result is user


@pytest.mark.asyncio
async def test_require_beta_access_missing_beta(monkeypatch):
    verify = auth_module.require_beta_access()
    user = _make_user(is_staff=False)

    class DummyBetaRepo:
        def __init__(self, db):
            self.db = db

        def get_latest_for_user(self, user_id):
            return None

    monkeypatch.setenv("SITE_MODE", "prod")
    monkeypatch.setattr(auth_module, "_preview_bypass", lambda *args, **kwargs: False)
    monkeypatch.setattr(auth_module, "_testing_bypass", lambda *args, **kwargs: False)
    monkeypatch.setattr(auth_module, "BetaAccessRepository", DummyBetaRepo)

    with pytest.raises(HTTPException) as exc:
        await verify(_make_request(), current_user=user, db=Mock())

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_beta_access_role_mismatch(monkeypatch):
    verify = auth_module.require_beta_access(role="instructor")
    user = _make_user(is_staff=False)

    class DummyBetaRepo:
        def __init__(self, db):
            self.db = db

        def get_latest_for_user(self, user_id):
            return SimpleNamespace(role="student")

    monkeypatch.setenv("SITE_MODE", "prod")
    monkeypatch.setattr(auth_module, "_preview_bypass", lambda *args, **kwargs: False)
    monkeypatch.setattr(auth_module, "_testing_bypass", lambda *args, **kwargs: False)
    monkeypatch.setattr(auth_module, "BetaAccessRepository", DummyBetaRepo)

    with pytest.raises(HTTPException) as exc:
        await verify(_make_request(), current_user=user, db=Mock())

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_beta_phase_access_preview(monkeypatch):
    verify_phase = auth_module.require_beta_phase_access()
    monkeypatch.setenv("SITE_MODE", "preview")

    result = await verify_phase(_make_request(), current_user=None, db=Mock())

    assert result is None


@pytest.mark.asyncio
async def test_require_beta_phase_access_requires_user(monkeypatch):
    verify_phase = auth_module.require_beta_phase_access()
    monkeypatch.setenv("SITE_MODE", "prod")
    monkeypatch.setattr(auth_module, "_testing_bypass", lambda *args, **kwargs: False)

    class DummySettingsRepo:
        def __init__(self, db):
            self.db = db

        def get_singleton(self):
            return SimpleNamespace(beta_disabled=False, beta_phase="instructor_only")

    async def _to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(auth_module, "BetaSettingsRepository", DummySettingsRepo)
    monkeypatch.setattr(auth_module.asyncio, "to_thread", _to_thread)

    with pytest.raises(HTTPException) as exc:
        await verify_phase(_make_request(), current_user=None, db=Mock())

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_beta_phase_access_open_phase(monkeypatch):
    verify_phase = auth_module.require_beta_phase_access()
    monkeypatch.setenv("SITE_MODE", "prod")
    monkeypatch.setattr(auth_module, "_testing_bypass", lambda *args, **kwargs: False)

    class DummySettingsRepo:
        def __init__(self, db):
            self.db = db

        def get_singleton(self):
            return SimpleNamespace(beta_disabled=False, beta_phase="open_beta")

    async def _to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(auth_module, "BetaSettingsRepository", DummySettingsRepo)
    monkeypatch.setattr(auth_module.asyncio, "to_thread", _to_thread)

    result = await verify_phase(_make_request(), current_user=None, db=Mock())

    assert result is None


@pytest.mark.asyncio
async def test_require_beta_phase_access_missing_beta(monkeypatch):
    verify_phase = auth_module.require_beta_phase_access()
    monkeypatch.setenv("SITE_MODE", "prod")
    monkeypatch.setattr(auth_module, "_testing_bypass", lambda *args, **kwargs: False)

    class DummySettingsRepo:
        def __init__(self, db):
            self.db = db

        def get_singleton(self):
            return SimpleNamespace(beta_disabled=False, beta_phase="instructor_only")

    class DummyBetaRepo:
        def __init__(self, db):
            self.db = db

        def get_latest_for_user(self, user_id):
            return None

    async def _to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(auth_module, "BetaSettingsRepository", DummySettingsRepo)
    monkeypatch.setattr(auth_module, "BetaAccessRepository", DummyBetaRepo)
    monkeypatch.setattr(auth_module.asyncio, "to_thread", _to_thread)

    with pytest.raises(HTTPException) as exc:
        await verify_phase(_make_request(), current_user=_make_user(is_staff=False), db=Mock())

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_beta_phase_access_beta_disabled(monkeypatch):
    verify_phase = auth_module.require_beta_phase_access()
    monkeypatch.setenv("SITE_MODE", "prod")
    monkeypatch.setattr(auth_module, "_testing_bypass", lambda *args, **kwargs: False)

    class DummySettingsRepo:
        def __init__(self, db):
            self.db = db

        def get_singleton(self):
            return SimpleNamespace(beta_disabled=True, beta_phase="instructor_only")

    async def _to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(auth_module, "BetaSettingsRepository", DummySettingsRepo)
    monkeypatch.setattr(auth_module.asyncio, "to_thread", _to_thread)

    result = await verify_phase(_make_request(), current_user=None, db=Mock())

    assert result is None
