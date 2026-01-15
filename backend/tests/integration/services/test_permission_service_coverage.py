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
