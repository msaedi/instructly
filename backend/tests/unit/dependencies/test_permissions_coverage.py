from __future__ import annotations

from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from app.dependencies import permissions as deps


@pytest.mark.asyncio
async def test_require_permission_allows_user():
    checker = deps.require_permission("perm.read")
    async def _has_perm(*_args, **_kwargs):
        return True

    permission_service = SimpleNamespace(user_has_permission_cached=_has_perm)
    user = SimpleNamespace(id="user-1")

    result = await checker(current_user=user, permission_service=permission_service)

    assert result is user


@pytest.mark.asyncio
async def test_require_permission_rejects_user():
    checker = deps.require_permission("perm.write")
    async def _has_perm(*_args, **_kwargs):
        return False

    permission_service = SimpleNamespace(user_has_permission_cached=_has_perm)
    user = SimpleNamespace(id="user-2")

    with pytest.raises(HTTPException) as exc:
        await checker(current_user=user, permission_service=permission_service)

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_any_permission_allows_first_match():
    checker = deps.require_any_permission("perm.a", "perm.b")

    async def _has_perm(_user_id, name):
        return name == "perm.b"

    permission_service = SimpleNamespace(user_has_permission_cached=_has_perm)
    user = SimpleNamespace(id="user-3")

    result = await checker(current_user=user, permission_service=permission_service)

    assert result is user


@pytest.mark.asyncio
async def test_require_any_permission_rejects_all_missing():
    checker = deps.require_any_permission("perm.a", "perm.b")

    async def _has_perm(_user_id, _name):
        return False

    permission_service = SimpleNamespace(user_has_permission_cached=_has_perm)
    user = SimpleNamespace(id="user-4")

    with pytest.raises(HTTPException) as exc:
        await checker(current_user=user, permission_service=permission_service)

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_all_permissions_rejects_missing():
    checker = deps.require_all_permissions("perm.a", "perm.b")

    async def _has_perm(_user_id, name):
        return name == "perm.a"

    permission_service = SimpleNamespace(user_has_permission_cached=_has_perm)
    user = SimpleNamespace(id="user-5")

    with pytest.raises(HTTPException) as exc:
        await checker(current_user=user, permission_service=permission_service)

    assert exc.value.status_code == 403
    assert "perm.b" in exc.value.detail


@pytest.mark.asyncio
async def test_require_role_accepts_role(monkeypatch):
    async def _to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(deps.asyncio, "to_thread", _to_thread)
    checker = deps.require_role("admin")
    permission_service = SimpleNamespace(get_user_roles=lambda _user_id: ["admin", "staff"])
    user = SimpleNamespace(id="user-6")

    result = await checker(current_user=user, permission_service=permission_service)

    assert result is user


@pytest.mark.asyncio
async def test_require_role_rejects_missing(monkeypatch):
    async def _to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(deps.asyncio, "to_thread", _to_thread)
    checker = deps.require_role("admin")
    permission_service = SimpleNamespace(get_user_roles=lambda _user_id: ["student"])
    user = SimpleNamespace(id="user-7")

    with pytest.raises(HTTPException) as exc:
        await checker(current_user=user, permission_service=permission_service)

    assert exc.value.status_code == 403


def test_permission_checker_caches_instances():
    checker = deps.PermissionChecker()

    first = checker.require("perm.read")
    second = checker.require("perm.read")

    assert first is second

    any_first = checker.require_any("a", "b")
    any_second = checker.require_any("b", "a")

    assert any_first is any_second

    all_first = checker.require_all("a", "b")
    all_second = checker.require_all("b", "a")

    assert all_first is all_second
