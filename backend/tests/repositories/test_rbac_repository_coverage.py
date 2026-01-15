import uuid

import pytest
from sqlalchemy.orm import Session

from app.models.rbac import Permission, Role, UserPermission
from app.repositories.rbac_repository import RBACRepository


def test_rbac_repository_happy_paths(db, test_student):
    repo = RBACRepository(db)

    perm_name = f"perm.{uuid.uuid4().hex[:8]}"
    role_name = f"role_{uuid.uuid4().hex[:8]}"

    permission = Permission(
        name=perm_name,
        description="Test permission",
        resource="tests",
        action="view",
    )
    role = Role(name=role_name, description="Test role")
    role.permissions.append(permission)

    db.add_all([permission, role])
    db.flush()

    user_perm = UserPermission(
        user_id=test_student.id, permission_id=permission.id, granted=True
    )
    db.add(user_perm)
    db.commit()

    assert repo.get_permission_by_name(perm_name) is not None
    assert any(p.name == perm_name for p in repo.get_all_permissions())

    assert repo.get_user_permission(test_student.id, permission.id) is not None
    assert repo.check_user_permission(test_student.id, perm_name) is not None
    assert repo.get_user_permissions(test_student.id)

    assert repo.get_role_by_name(role_name) is not None
    assert any(r.name == role_name for r in repo.get_all_roles())

    role_perms = repo.get_role_permissions(role_name)
    assert any(p.name == perm_name for p in role_perms)

    assert repo.get_user_by_id(test_student.id) is not None
    assert repo.permission_exists(perm_name)
    assert repo.role_exists(role_name)


def test_rbac_repository_error_paths(db, monkeypatch):
    repo = RBACRepository(db)

    def _boom(*_args, **_kwargs):
        raise RuntimeError("db failure")

    monkeypatch.setattr(Session, "query", _boom, raising=False)

    assert repo.get_permission_by_name("missing") is None
    assert repo.get_all_permissions() == []
    assert repo.get_user_permission("u", "p") is None
    assert repo.check_user_permission("u", "perm") is None
    assert repo.get_user_permissions("u") == []
    assert repo.get_role_by_name("role") is None
    assert repo.get_all_roles() == []
    assert repo.get_role_permissions("role") == []
    assert repo.get_user_by_id("u") is None


def test_rbac_repository_add_user_permission_raises(db, test_student, monkeypatch):
    repo = RBACRepository(db)

    perm = Permission(name=f"perm.{uuid.uuid4().hex[:8]}")
    db.add(perm)
    db.flush()

    def _add_boom(*_args, **_kwargs):
        raise RuntimeError("add failed")

    monkeypatch.setattr(repo.db, "add", _add_boom)

    with pytest.raises(RuntimeError):
        repo.add_user_permission(test_student.id, perm.id, granted=True)
