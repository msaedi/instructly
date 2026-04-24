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


def _dummy_request():
    return SimpleNamespace(headers={}, client=None)


def _dummy_user():
    return SimpleNamespace(id="user-1", email="user@example.com", first_name="Alex")


class _NotificationStub:
    def __init__(self):
        self.deleted_confirmations: list[dict[str, str | None]] = []
        self.anonymized_confirmations: list[dict[str, str | None]] = []

    def send_account_deleted_confirmation(self, *, to_email: str, first_name: str | None):
        self.deleted_confirmations.append({"to_email": to_email, "first_name": first_name})
        return True

    def send_account_anonymized_confirmation(self, *, to_email: str, first_name: str | None):
        self.anonymized_confirmations.append({"to_email": to_email, "first_name": first_name})
        return True


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
    notification_service = _NotificationStub()

    with pytest.raises(HTTPException) as exc:
        await routes.delete_my_data(
            request=UserDataDeletionRequest(delete_account=True),
            http_request=_dummy_request(),
            current_user=_dummy_user(),
            db=None,
            notification_service=notification_service,
        )

    assert exc.value.status_code == 400
    assert notification_service.deleted_confirmations == []


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
            http_request=_dummy_request(),
            current_user=_dummy_user(),
            db=None,
            notification_service=_NotificationStub(),
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
            http_request=_dummy_request(),
            current_user=SimpleNamespace(),
            db=None,
        )

    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_delete_my_data_audit_failure_delete_account(monkeypatch):
    class _ServiceStub:
        def __init__(self, _db):
            pass

        def delete_user_data(self, *_args, **_kwargs):
            return {"ok": True}

    monkeypatch.setattr(routes, "PrivacyService", _ServiceStub)
    monkeypatch.setattr(
        routes.RepositoryFactory,
        "create_user_repository",
        lambda _db: SimpleNamespace(invalidate_all_tokens=lambda *_args, **_kwargs: True),
    )

    def _boom(*_args, **_kwargs):
        raise RuntimeError("audit failed")

    monkeypatch.setattr(routes.AuditService, "log", _boom)

    response = await routes.delete_my_data(
        request=UserDataDeletionRequest(delete_account=True),
        http_request=_dummy_request(),
        current_user=_dummy_user(),
        db=None,
        notification_service=_NotificationStub(),
    )

    assert response.account_deleted is True


@pytest.mark.asyncio
async def test_delete_my_data_audit_failure_anonymize(monkeypatch):
    class _ServiceStub:
        def __init__(self, _db):
            pass

        def anonymize_user(self, *_args, **_kwargs):
            return True

    monkeypatch.setattr(routes, "PrivacyService", _ServiceStub)
    monkeypatch.setattr(
        routes.RepositoryFactory,
        "create_user_repository",
        lambda _db: SimpleNamespace(invalidate_all_tokens=lambda *_args, **_kwargs: True),
    )

    def _boom(*_args, **_kwargs):
        raise RuntimeError("audit failed")

    monkeypatch.setattr(routes.AuditService, "log", _boom)

    response = await routes.delete_my_data(
        request=UserDataDeletionRequest(delete_account=False),
        http_request=_dummy_request(),
        current_user=_dummy_user(),
        db=None,
        notification_service=_NotificationStub(),
    )

    assert response.account_deleted is False


@pytest.mark.asyncio
async def test_delete_user_data_admin_audit_failure(monkeypatch):
    class _ServiceStub:
        def __init__(self, _db):
            pass

        def delete_user_data(self, *_args, **_kwargs):
            return {"ok": True}

    monkeypatch.setattr(routes, "PrivacyService", _ServiceStub)
    monkeypatch.setattr(
        routes.RepositoryFactory,
        "create_user_repository",
        lambda _db: SimpleNamespace(invalidate_all_tokens=lambda *_args, **_kwargs: True),
    )
    monkeypatch.setattr(
        routes,
        "capture_sentry_exception",
        lambda *_args, **_kwargs: None,
    )

    def _boom(*_args, **_kwargs):
        raise RuntimeError("audit failed")

    monkeypatch.setattr(routes.AuditService, "log", _boom)

    response = await routes.delete_user_data_admin(
        user_id="user-1",
        request=UserDataDeletionRequest(delete_account=True),
        http_request=_dummy_request(),
        current_user=SimpleNamespace(id="admin-1"),
        db=None,
    )

    assert response.account_deleted is True
