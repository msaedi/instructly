from __future__ import annotations

from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from app.routes.v1 import privacy as routes
from app.schemas.privacy import UserDataDeletionRequest


class _AuthServiceStub:
    def __init__(self, user=None):
        self._user = user

    def get_user_by_email(self, _email):
        return self._user


@pytest.mark.asyncio
async def test_get_current_user_raises_not_found():
    with pytest.raises(HTTPException) as exc:
        await routes.get_current_user(
            current_user_email="missing@example.com",
            auth_service=_AuthServiceStub(user=None),
        )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_my_data_value_error(monkeypatch):
    class _ServiceStub:
        def __init__(self, _db):
            pass

        def delete_user_data(self, *_args, **_kwargs):
            raise ValueError("nope")

    monkeypatch.setattr(routes, "PrivacyService", _ServiceStub)

    with pytest.raises(HTTPException) as exc:
        await routes.delete_my_data(
            request=UserDataDeletionRequest(delete_account=True),
            current_user=SimpleNamespace(id="user-1"),
            db=None,
        )

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_delete_my_data_anonymize_failure(monkeypatch):
    class _ServiceStub:
        def __init__(self, _db):
            pass

        def anonymize_user(self, *_args, **_kwargs):
            return False

    monkeypatch.setattr(routes, "PrivacyService", _ServiceStub)

    with pytest.raises(HTTPException) as exc:
        await routes.delete_my_data(
            request=UserDataDeletionRequest(delete_account=False),
            current_user=SimpleNamespace(id="user-1"),
            db=None,
        )

    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_privacy_statistics_error(monkeypatch):
    class _ServiceStub:
        def __init__(self, _db):
            pass

        def get_privacy_statistics(self):
            raise RuntimeError("boom")

    monkeypatch.setattr(routes, "PrivacyService", _ServiceStub)

    with pytest.raises(HTTPException) as exc:
        await routes.get_privacy_statistics(current_user=SimpleNamespace(), db=None)

    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_apply_retention_policies_error(monkeypatch):
    class _ServiceStub:
        def __init__(self, _db):
            pass

        def apply_retention_policies(self):
            raise RuntimeError("boom")

    monkeypatch.setattr(routes, "PrivacyService", _ServiceStub)

    with pytest.raises(HTTPException) as exc:
        await routes.apply_retention_policies(current_user=SimpleNamespace(), db=None)

    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_export_user_data_admin_error(monkeypatch):
    class _ServiceStub:
        def __init__(self, _db):
            pass

        def export_user_data(self, _user_id):
            raise RuntimeError("boom")

    monkeypatch.setattr(routes, "PrivacyService", _ServiceStub)

    with pytest.raises(HTTPException) as exc:
        await routes.export_user_data_admin(
            user_id="user-1",
            current_user=SimpleNamespace(),
            db=None,
        )

    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_delete_user_data_admin_error(monkeypatch):
    class _ServiceStub:
        def __init__(self, _db):
            pass

        def delete_user_data(self, *_args, **_kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(routes, "PrivacyService", _ServiceStub)

    with pytest.raises(HTTPException) as exc:
        await routes.delete_user_data_admin(
            user_id="user-1",
            request=UserDataDeletionRequest(delete_account=True),
            current_user=SimpleNamespace(),
            db=None,
        )

    assert exc.value.status_code == 500
