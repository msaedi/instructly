from __future__ import annotations

from fastapi import HTTPException
import pytest
from starlette.requests import Request

from app.routes.v1.admin import users as users_routes


def _make_request() -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/admin/users/target/force-logout",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_force_logout_user_success(monkeypatch, db, admin_user):
    calls: list[str] = []
    triggers: list[str | None] = []
    audit_calls: list[dict[str, object]] = []

    class _Repo:
        def invalidate_all_tokens(self, user_id: str, **_kwargs):
            calls.append(user_id)
            triggers.append(_kwargs.get("trigger") if _kwargs else None)
            return True

    class _AuditService:
        def __init__(self, _db):
            pass

        def log(self, **kwargs):
            audit_calls.append(kwargs)

    monkeypatch.setattr(
        users_routes.RepositoryFactory,
        "create_user_repository",
        lambda _db: _Repo(),
    )
    monkeypatch.setattr(users_routes, "AuditService", _AuditService)

    response = await users_routes.force_logout_user(
        user_id="01USERIDFORCELOGOUT00000000",
        request=_make_request(),
        current_admin=admin_user,
        db=db,
    )
    assert response.message == "User sessions have been logged out"
    assert calls == ["01USERIDFORCELOGOUT00000000"]
    assert triggers == ["admin_force_logout"]
    assert len(audit_calls) == 1
    assert audit_calls[0]["action"] == "admin.force_logout"
    assert audit_calls[0]["resource_id"] == "01USERIDFORCELOGOUT00000000"


@pytest.mark.asyncio
async def test_force_logout_user_not_found(monkeypatch, db, admin_user):
    class _Repo:
        def invalidate_all_tokens(self, _user_id: str, **_kwargs):
            return False

    monkeypatch.setattr(
        users_routes.RepositoryFactory,
        "create_user_repository",
        lambda _db: _Repo(),
    )

    with pytest.raises(HTTPException) as exc:
        await users_routes.force_logout_user(
            user_id="missing-user",
            request=_make_request(),
            current_admin=admin_user,
            db=db,
        )
    assert exc.value.status_code == 404
