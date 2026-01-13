from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import HTTPException
import pytest
from starlette.requests import Request

from app.api.dependencies import auth as auth_deps
from app.api.dependencies.authz import (
    _cookie_auth_allowed,
    _dependency_requires_auth,
    _norm,
    public_guard,
    require_roles,
    require_scopes,
    requires_roles,
    requires_scopes,
)
from app.dependencies.permissions import require_permission


def _make_request(path: str, headers: dict | None = None) -> Request:
    raw_headers = []
    for key, value in (headers or {}).items():
        raw_headers.append((key.encode(), value.encode()))
    scope = {
        "type": "http",
        "path": path,
        "headers": raw_headers,
        "query_string": b"",
        "client": ("127.0.0.1", 123),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_require_roles_allows_when_role_present():
    checker = require_roles("admin")
    permission_service = Mock()
    permission_service.get_user_roles.return_value = ["Admin", "Other"]
    user = SimpleNamespace(id="user-1")

    result = await checker(current_user=user, permission_service=permission_service)

    assert result is user


@pytest.mark.asyncio
async def test_require_roles_rejects_when_missing():
    checker = require_roles("admin")
    permission_service = Mock()
    permission_service.get_user_roles.return_value = ["student"]
    user = SimpleNamespace(id="user-2")

    with pytest.raises(HTTPException) as exc:
        await checker(current_user=user, permission_service=permission_service)

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_scopes_requires_all():
    checker = require_scopes("perm:a", "perm:b")
    permission_service = Mock()
    permission_service.user_has_permission.side_effect = [True, True]
    user = SimpleNamespace(id="user-3")

    result = await checker(current_user=user, permission_service=permission_service)

    assert result is user


@pytest.mark.asyncio
async def test_require_scopes_rejects_missing():
    checker = require_scopes("perm:a", "perm:b")
    permission_service = Mock()
    permission_service.user_has_permission.side_effect = [True, False]
    user = SimpleNamespace(id="user-4")

    with pytest.raises(HTTPException) as exc:
        await checker(current_user=user, permission_service=permission_service)

    assert exc.value.status_code == 403


def test_requires_roles_sets_attribute():
    @requires_roles("admin", "staff")
    async def handler():
        return None

    assert handler._required_roles == ["admin", "staff"]


def test_requires_scopes_sets_attribute():
    @requires_scopes("perm:a")
    async def handler():
        return None

    assert handler._required_scopes == ["perm:a"]


def test_norm_strips_and_lowercases():
    assert _norm(" TeSt ") == "test"


def test_cookie_auth_allowed_explicit_and_env():
    assert _cookie_auth_allowed("dev") is True
    assert _cookie_auth_allowed("preview") is False
    assert _cookie_auth_allowed("dev", explicit=False) is False
    assert _cookie_auth_allowed("dev", explicit=True) is True


def test_dependency_requires_auth_guard_is_false():
    guard = public_guard()
    assert _dependency_requires_auth(guard) is False


def test_dependency_requires_auth_optional_is_false():
    assert _dependency_requires_auth(auth_deps.get_current_active_user_optional) is False


def test_dependency_requires_auth_required_is_true():
    assert _dependency_requires_auth(auth_deps.get_current_user) is True


def test_dependency_requires_auth_permissions_module_true():
    perm_dep = require_permission("perm")
    assert _dependency_requires_auth(perm_dep) is True


def test_dependency_requires_auth_auth_module_non_required_false():
    def _dummy():
        return None

    _dummy.__module__ = "app.api.dependencies.auth"
    _dummy.__name__ = "get_current_user_optional"

    assert _dependency_requires_auth(_dummy) is False


def test_dependency_requires_auth_other_module_false():
    def _dummy():
        return None

    _dummy.__module__ = "other.module"
    _dummy.__name__ = "noop"

    assert _dependency_requires_auth(_dummy) is False


@pytest.mark.asyncio
async def test_public_guard_allows_open_path(monkeypatch):
    guard = public_guard(open_paths=["/api/v1/bookings"])
    request = _make_request("/api/v1/bookings")

    monkeypatch.setattr("app.api.dependencies.authz.get_user_from_bearer_header", lambda *a: None)
    monkeypatch.setattr("app.api.dependencies.authz.get_user_from_session_cookie", lambda *a: None)

    result = await guard(request, db=Mock())

    assert result is None


@pytest.mark.asyncio
async def test_public_guard_sets_user_from_bearer(monkeypatch):
    guard = public_guard()
    request = _make_request("/api/v1/other")
    user = SimpleNamespace(id="user-5")

    monkeypatch.setattr("app.api.dependencies.authz.get_user_from_bearer_header", lambda *a: user)
    monkeypatch.setattr("app.api.dependencies.authz.get_user_from_session_cookie", lambda *a: None)

    result = await guard(request, db=Mock())

    assert result is user
    assert request.state.current_user is user


@pytest.mark.asyncio
async def test_public_guard_requires_auth_missing_user(monkeypatch):
    guard = public_guard()
    request = _make_request("/api/v1/private")

    dependency = SimpleNamespace(call=auth_deps.get_current_user)
    request.scope["route"] = SimpleNamespace(dependant=SimpleNamespace(dependencies=[dependency]))

    monkeypatch.setattr("app.api.dependencies.authz.get_user_from_bearer_header", lambda *a: None)
    monkeypatch.setattr("app.api.dependencies.authz.get_user_from_session_cookie", lambda *a: None)

    with pytest.raises(HTTPException) as exc:
        await guard(request, db=Mock())

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_public_guard_preview_prefix_allows(monkeypatch):
    guard = public_guard()
    request = _make_request("/api/v1/bookings/123")

    monkeypatch.setenv("SITE_MODE", "preview")
    monkeypatch.setenv("PHASE", "")

    monkeypatch.setattr("app.api.dependencies.authz.get_user_from_bearer_header", lambda *a: None)
    monkeypatch.setattr("app.api.dependencies.authz.get_user_from_session_cookie", lambda *a: None)

    result = await guard(request, db=Mock())

    assert result is None
