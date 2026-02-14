from __future__ import annotations

from fastapi import HTTPException
import pytest

from app.routes.v1.admin import users as users_routes


@pytest.mark.asyncio
async def test_force_logout_user_success(monkeypatch, db, admin_user):
    calls: list[str] = []

    class _Repo:
        def invalidate_all_tokens(self, user_id: str):
            calls.append(user_id)
            return True

    monkeypatch.setattr(
        users_routes.RepositoryFactory,
        "create_user_repository",
        lambda _db: _Repo(),
    )

    response = await users_routes.force_logout_user(
        user_id="01USERIDFORCELOGOUT00000000",
        _=admin_user,
        db=db,
    )
    assert response.message == "User sessions have been logged out"
    assert calls == ["01USERIDFORCELOGOUT00000000"]


@pytest.mark.asyncio
async def test_force_logout_user_not_found(monkeypatch, db, admin_user):
    class _Repo:
        def invalidate_all_tokens(self, _user_id: str):
            return False

    monkeypatch.setattr(
        users_routes.RepositoryFactory,
        "create_user_repository",
        lambda _db: _Repo(),
    )

    with pytest.raises(HTTPException) as exc:
        await users_routes.force_logout_user(
            user_id="missing-user",
            _=admin_user,
            db=db,
        )
    assert exc.value.status_code == 404
