from contextlib import contextmanager

from fastapi import HTTPException, Request, Response
import pytest

from app.auth import create_temp_token
from app.routes.v1 import two_factor_auth as routes
from app.schemas.security import (
    BackupCodesResponse,
    TFADisableRequest,
    TFASetupVerifyRequest,
    TFAVerifyLoginRequest,
)


class _AuthService:
    def __init__(self, user):
        self._user = user

    def get_current_user(self, *, email):
        return self._user


class _TFAService:
    def __init__(self, db, verify_ok=True):
        self.db = db
        self._verify_ok = verify_ok

    def setup_initiate(self, _user):
        return {
            "secret": "secret",
            "qr_code_data_url": "data:image/png;base64,xyz",
            "otpauth_url": "otpauth://test",
        }

    def setup_verify(self, _user, _code):
        return ["code1", "code2"]

    def disable(self, _user, _password):
        return None

    def status(self, user):
        return {"enabled": bool(getattr(user, "totp_enabled", False))}

    def generate_backup_codes(self):
        return ["code1", "code2"]

    def verify_login(self, _user, **_kwargs):
        return self._verify_ok

    @contextmanager
    def transaction(self):
        yield


def _make_request(headers=None):
    scope = {
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
    }
    return Request(scope)


def test_setup_initiate_and_status(db, test_student):
    auth_service = _AuthService(test_student)
    tfa_service = _TFAService(db)

    init_response = routes.setup_initiate(
        current_user=test_student.email,
        auth_service=auth_service,
        tfa_service=tfa_service,
    )
    assert init_response.secret

    status = routes.status_endpoint(
        current_user=test_student.email,
        auth_service=auth_service,
        tfa_service=tfa_service,
    )
    assert status.enabled is False


def test_setup_verify_success_and_failure(db, test_student, monkeypatch):
    auth_service = _AuthService(test_student)
    tfa_service = _TFAService(db)

    class _Notify:
        def __init__(self, *_args, **_kwargs):
            pass

        def send_two_factor_changed_notification(self, **_kwargs):
            raise RuntimeError("notify")

    monkeypatch.setattr("app.routes.v1.two_factor_auth.NotificationService", _Notify)

    response = routes.setup_verify(
        TFASetupVerifyRequest(code="123456"),
        Response(),
        _make_request(),
        current_user=test_student.email,
        auth_service=auth_service,
        tfa_service=tfa_service,
    )
    assert response.enabled is True

    class _BadService(_TFAService):
        def setup_verify(self, _user, _code):
            raise ValueError("bad")

    with pytest.raises(HTTPException) as exc:
        routes.setup_verify(
            TFASetupVerifyRequest(code="123456"),
            Response(),
            _make_request(),
            current_user=test_student.email,
            auth_service=auth_service,
            tfa_service=_BadService(db),
        )
    assert exc.value.status_code == 400


def test_setup_verify_invalidates_all_tokens(db, test_student, monkeypatch):
    auth_service = _AuthService(test_student)
    tfa_service = _TFAService(db)
    calls: list[str] = []
    triggers: list[str | None] = []

    class _Repo:
        def invalidate_all_tokens(self, user_id: str, **_kwargs):
            calls.append(user_id)
            triggers.append(_kwargs.get("trigger") if _kwargs else None)
            return True

    monkeypatch.setattr(
        routes.RepositoryFactory,
        "create_user_repository",
        lambda _db: _Repo(),
    )

    response = routes.setup_verify(
        TFASetupVerifyRequest(code="123456"),
        Response(),
        _make_request(),
        current_user=test_student.email,
        auth_service=auth_service,
        tfa_service=tfa_service,
    )
    assert response.enabled is True
    assert calls == [test_student.id]
    assert triggers == ["2fa_change"]


def test_disable_success_and_failure(db, test_student, monkeypatch):
    auth_service = _AuthService(test_student)

    class _Notify:
        def __init__(self, *_args, **_kwargs):
            pass

        def send_two_factor_changed_notification(self, **_kwargs):
            raise RuntimeError("notify")

    monkeypatch.setattr("app.routes.v1.two_factor_auth.NotificationService", _Notify)

    response = routes.disable(
        TFADisableRequest(current_password="password"),
        Response(),
        _make_request(),
        current_user=test_student.email,
        auth_service=auth_service,
        tfa_service=_TFAService(db),
    )
    assert response.message

    class _BadService(_TFAService):
        def disable(self, _user, _password):
            raise ValueError("bad")

    with pytest.raises(HTTPException) as exc:
        routes.disable(
            TFADisableRequest(current_password="bad"),
            Response(),
            _make_request(),
            current_user=test_student.email,
            auth_service=auth_service,
            tfa_service=_BadService(db),
        )
    assert exc.value.status_code == 400


def test_disable_invalidates_all_tokens(db, test_student, monkeypatch):
    auth_service = _AuthService(test_student)
    calls: list[str] = []
    triggers: list[str | None] = []

    class _Repo:
        def invalidate_all_tokens(self, user_id: str, **_kwargs):
            calls.append(user_id)
            triggers.append(_kwargs.get("trigger") if _kwargs else None)
            return True

    monkeypatch.setattr(
        routes.RepositoryFactory,
        "create_user_repository",
        lambda _db: _Repo(),
    )

    response = routes.disable(
        TFADisableRequest(current_password="password"),
        Response(),
        _make_request(),
        current_user=test_student.email,
        auth_service=auth_service,
        tfa_service=_TFAService(db),
    )
    assert response.message
    assert calls == [test_student.id]
    assert triggers == ["2fa_change"]


def test_setup_verify_audit_failure(db, test_student, monkeypatch):
    auth_service = _AuthService(test_student)
    tfa_service = _TFAService(db)

    def _boom(*_args, **_kwargs):
        raise RuntimeError("audit failed")

    monkeypatch.setattr(routes.AuditService, "log_changes", _boom)

    response = routes.setup_verify(
        TFASetupVerifyRequest(code="123456"),
        Response(),
        _make_request(),
        current_user=test_student.email,
        auth_service=auth_service,
        tfa_service=tfa_service,
    )
    assert response.enabled is True


def test_disable_audit_failure(db, test_student, monkeypatch):
    auth_service = _AuthService(test_student)
    tfa_service = _TFAService(db)

    def _boom(*_args, **_kwargs):
        raise RuntimeError("audit failed")

    monkeypatch.setattr(routes.AuditService, "log_changes", _boom)

    response = routes.disable(
        TFADisableRequest(current_password="password"),
        Response(),
        _make_request(),
        current_user=test_student.email,
        auth_service=auth_service,
        tfa_service=tfa_service,
    )
    assert response.message


def test_regenerate_backup_codes(db, test_student):
    auth_service = _AuthService(test_student)
    tfa_service = _TFAService(db)

    response = routes.regenerate_backup_codes(
        current_user=test_student.email,
        auth_service=auth_service,
        tfa_service=tfa_service,
    )
    assert isinstance(response, BackupCodesResponse)
    assert response.backup_codes


def test_verify_login_invalid_token(db, test_student):
    auth_service = _AuthService(test_student)
    tfa_service = _TFAService(db)

    with pytest.raises(HTTPException) as exc:
        routes.verify_login(
            TFAVerifyLoginRequest(temp_token="bad", code="123"),
            _make_request(),
            Response(),
            auth_service=auth_service,
            tfa_service=tfa_service,
        )
    assert exc.value.status_code == 400


def test_verify_login_not_enabled(db, test_student):
    auth_service = _AuthService(test_student)
    tfa_service = _TFAService(db)

    token = create_temp_token({"sub": test_student.email, "tfa_pending": True})
    with pytest.raises(HTTPException) as exc:
        routes.verify_login(
            TFAVerifyLoginRequest(temp_token=token, code="123"),
            _make_request(),
            Response(),
            auth_service=auth_service,
            tfa_service=tfa_service,
        )
    assert exc.value.status_code == 400


def test_verify_login_success_with_trust_and_guest_conversion_error(db, test_student, monkeypatch):
    test_student.totp_enabled = True
    db.commit()

    auth_service = _AuthService(test_student)
    tfa_service = _TFAService(db, verify_ok=True)

    def _convert_boom(*_args, **_kwargs):
        raise RuntimeError("convert")

    monkeypatch.setattr(
        "app.routes.v1.two_factor_auth.SearchHistoryService.convert_guest_searches_to_user",
        _convert_boom,
    )

    token = create_temp_token(
        {"sub": test_student.email, "tfa_pending": True, "guest_session_id": "guest"}
    )
    response = Response()
    result = routes.verify_login(
        TFAVerifyLoginRequest(temp_token=token, code="123"),
        _make_request({"X-Trust-Browser": "true"}),
        response,
        auth_service=auth_service,
        tfa_service=tfa_service,
    )

    assert result.token_type is None
    assert result.access_token is None
    assert any(
        "tfa_trusted" in cookie for cookie in response.headers.getlist("set-cookie")
    )
