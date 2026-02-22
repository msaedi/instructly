from __future__ import annotations

import asyncio

import pytest

from app.core import config as app_config
from app.core.enums import PermissionName, RoleName
from app.services.permission_service import PermissionService


def test_user_has_permission_and_cache(db, test_student):
    service = PermissionService(db)

    assert isinstance(
        service.user_has_permission(test_student.id, PermissionName.VIEW_MESSAGES), bool
    )
    service._cache[f"{test_student.id}:{PermissionName.VIEW_MESSAGES.value}"] = True
    assert service.user_has_permission(test_student.id, PermissionName.VIEW_MESSAGES) is True
    assert service.user_has_permission("missing-user", PermissionName.VIEW_MESSAGES) is False


def test_grant_and_revoke_permission(db, test_student):
    service = PermissionService(db)

    assert service.grant_permission(test_student.id, PermissionName.ADMIN_READ.value) is True
    assert service.user_has_permission(test_student.id, PermissionName.ADMIN_READ) is True

    assert service.revoke_permission(test_student.id, PermissionName.ADMIN_READ.value) is True
    assert service.user_has_permission(test_student.id, PermissionName.ADMIN_READ) is False
    assert service.grant_permission(test_student.id, "missing-permission") is False
    assert service.revoke_permission(test_student.id, "missing-permission") is False


def test_user_permissions_and_roles(db, test_student):
    service = PermissionService(db)
    roles = service.get_user_roles(test_student.id)
    assert RoleName.STUDENT.value in roles

    permissions = service.get_user_permissions(test_student.id)
    assert isinstance(permissions, set)
    assert service.get_user_permissions("missing-user") == set()

    assert service.revoke_permission(test_student.id, PermissionName.VIEW_MESSAGES.value) is True
    permissions = service.get_user_permissions(test_student.id)
    assert PermissionName.VIEW_MESSAGES.value not in permissions


@pytest.mark.asyncio
async def test_permissions_cached_paths(db, test_student, monkeypatch):
    service = PermissionService(db)

    async def fake_get_cached(_user_id):
        return None

    async def fake_set_cached(_user_id, _permissions):
        return None

    monkeypatch.setattr("app.services.permission_service.get_cached_permissions", fake_get_cached)
    monkeypatch.setattr("app.services.permission_service.set_cached_permissions", fake_set_cached)

    perms = await service.get_user_permissions_cached(test_student.id)
    assert isinstance(perms, set)

    has_perm = await service.user_has_permission_cached(test_student.id, PermissionName.VIEW_MESSAGES)
    assert isinstance(has_perm, bool)


def test_assign_and_remove_role(db, test_student):
    service = PermissionService(db)

    assert service.assign_role(test_student.id, RoleName.ADMIN.value) is True
    assert RoleName.ADMIN.value in service.get_user_roles(test_student.id)

    assert service.remove_role(test_student.id, RoleName.ADMIN.value) is True
    assert RoleName.ADMIN.value not in service.get_user_roles(test_student.id)
    assert service.assign_role(test_student.id, "missing-role") is False
    assert service.remove_role(test_student.id, RoleName.ADMIN.value) is False


def test_clear_cache(db, test_student):
    service = PermissionService(db)
    service._cache[f"{test_student.id}:{PermissionName.VIEW_MESSAGES.value}"] = True
    service.clear_cache()
    assert service._cache == {}


@pytest.mark.asyncio
async def test_clear_user_cache_async_paths(db, test_student, monkeypatch):
    service = PermissionService(db)
    service._cache[f"{test_student.id}:{PermissionName.VIEW_MESSAGES.value}"] = True

    async def fake_invalidate(_user_id: str) -> None:
        return None

    monkeypatch.setattr(
        "app.services.permission_service.invalidate_cached_permissions", fake_invalidate
    )

    await service._clear_user_cache_async(test_student.id)
    assert service._cache == {}


@pytest.mark.asyncio
async def test_clear_user_cache_sync_with_running_loop(db, test_student, monkeypatch):
    service = PermissionService(db)
    service._cache[f"{test_student.id}:{PermissionName.VIEW_MESSAGES.value}"] = True

    async def fake_invalidate(_user_id: str) -> None:
        return None

    monkeypatch.setattr(
        "app.services.permission_service.invalidate_cached_permissions", fake_invalidate
    )
    monkeypatch.setattr(app_config.settings, "is_testing", False)

    service._clear_user_cache(test_student.id)
    await asyncio.sleep(0)
    assert service._cache == {}


# ── Coverage tests for missed lines ──


def test_user_has_permission_no_role_match_no_override_returns_false(db, test_student):
    """user_has_permission returns False when no role permission AND no user override (lines 100-101).

    This tests the fallthrough path after checking role permissions and individual
    overrides where neither grants the permission.
    """
    service = PermissionService(db)
    # Clear any cached data
    service.clear_cache()

    # Use a permission the student definitely does NOT have through roles or overrides
    result = service.user_has_permission(test_student.id, "nonexistent.permission.xyz")
    assert result is False
    # Verify it was cached as False
    assert service._cache.get(f"{test_student.id}:nonexistent.permission.xyz") is False


def test_get_user_roles_missing_user_returns_empty_list(db):
    """get_user_roles returns [] when user is not found (line 207)."""
    service = PermissionService(db)
    result = service.get_user_roles("01NONEXISTENT0000000000000")
    assert result == []


def test_grant_permission_updates_existing_override(db, test_student):
    """grant_permission updates existing user_perm when override already exists (line 236).

    First revoke a permission (creates override with granted=False),
    then grant it (should update existing override to granted=True).
    """
    service = PermissionService(db)

    perm_name = PermissionName.ADMIN_READ.value

    # First, grant it (creates an override)
    assert service.grant_permission(test_student.id, perm_name) is True
    service.clear_cache()

    # Revoke it (updates the existing override to granted=False)
    assert service.revoke_permission(test_student.id, perm_name) is True
    service.clear_cache()

    # Grant it again — this time user_perm already exists, so it goes through line 236
    assert service.grant_permission(test_student.id, perm_name) is True
    service.clear_cache()

    # Verify permission is granted
    assert service.user_has_permission(test_student.id, PermissionName.ADMIN_READ) is True


def test_assign_role_already_has_role_returns_false(db, test_student):
    """assign_role returns False when user already has the role (line 304)."""
    service = PermissionService(db)

    # Student already has STUDENT role by default
    result = service.assign_role(test_student.id, RoleName.STUDENT.value)
    assert result is False


def test_remove_role_not_present_returns_false(db, test_student):
    """remove_role returns False when user doesn't have the role (line 332)."""
    service = PermissionService(db)

    # Student doesn't have ADMIN role
    result = service.remove_role(test_student.id, RoleName.ADMIN.value)
    assert result is False


def test_remove_role_missing_user_returns_false(db):
    """remove_role returns False when user doesn't exist (line 331)."""
    service = PermissionService(db)
    result = service.remove_role("01NONEXISTENT0000000000000", RoleName.STUDENT.value)
    assert result is False


@pytest.mark.asyncio
async def test_clear_user_cache_task_exception_callback(db, test_student, monkeypatch):
    """_consume_task_exception callback in _clear_user_cache consumes task exception (line 365-368)."""
    service = PermissionService(db)
    service._cache[f"{test_student.id}:{PermissionName.VIEW_MESSAGES.value}"] = True

    callback_holder = []

    class StubTask:
        def __init__(self):
            self._callbacks = []

        def add_done_callback(self, fn):
            self._callbacks.append(fn)
            callback_holder.append(fn)

    class StubLoop:
        def create_task(self, coro):
            coro.close()
            return StubTask()

    async def fake_invalidate(_user_id):
        return None

    monkeypatch.setattr(
        "app.services.permission_service.invalidate_cached_permissions", fake_invalidate
    )
    monkeypatch.setattr(app_config.settings, "is_testing", False)
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: StubLoop())

    service._clear_user_cache(test_student.id)
    assert service._cache == {}

    # Verify callback was registered and exercise it
    assert len(callback_holder) == 1
    cb = callback_holder[0]

    # Test with a cancelled task
    class CancelledTask:
        def cancelled(self):
            return True

        def exception(self):
            raise AssertionError("should not be called")

    cb(CancelledTask())  # Should not raise

    # Test with a task that has an exception
    class FailedTask:
        def cancelled(self):
            return False

        def exception(self):
            return RuntimeError("redis down")

    cb(FailedTask())  # Should consume the exception without raising


def test_clear_user_cache_no_event_loop_uses_anyio(db, test_student, monkeypatch):
    """_clear_user_cache uses anyio fallback when no running event loop (line 371-375)."""
    service = PermissionService(db)
    service._cache[f"{test_student.id}:{PermissionName.VIEW_MESSAGES.value}"] = True

    invalidated = []

    async def fake_invalidate(user_id):
        invalidated.append(user_id)

    monkeypatch.setattr(
        "app.services.permission_service.invalidate_cached_permissions", fake_invalidate
    )
    # Simulate no running event loop
    monkeypatch.setattr(
        asyncio, "get_running_loop", lambda: (_ for _ in ()).throw(RuntimeError("no loop"))
    )

    # Patch anyio.from_thread.run to just run the coroutine
    import anyio

    def fake_from_thread_run(fn, *args):
        # Run the async function synchronously
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(fn(*args))
        finally:
            loop.close()

    monkeypatch.setattr(anyio.from_thread, "run", fake_from_thread_run)

    service._clear_user_cache(test_student.id)
    assert service._cache == {}
    assert test_student.id in invalidated


def test_clear_user_cache_redis_failure_is_best_effort(db, test_student, monkeypatch):
    """_clear_user_cache swallows Redis exceptions (line 376-378)."""
    service = PermissionService(db)
    service._cache[f"{test_student.id}:{PermissionName.VIEW_MESSAGES.value}"] = True

    # Simulate no running event loop
    monkeypatch.setattr(
        asyncio, "get_running_loop", lambda: (_ for _ in ()).throw(RuntimeError("no loop"))
    )

    import anyio

    def fail_run(fn, *args):
        raise Exception("anyio failure")

    monkeypatch.setattr(anyio.from_thread, "run", fail_run)

    # Should not raise — Redis invalidation is best-effort
    service._clear_user_cache(test_student.id)
    # In-memory cache should still be cleared
    assert service._cache == {}
