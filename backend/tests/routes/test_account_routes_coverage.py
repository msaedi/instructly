from __future__ import annotations

from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from app.core.exceptions import BusinessRuleException, ValidationException
from app.routes.v1 import account as account_routes
from app.services.account_lifecycle_service import AccountLifecycleService
from app.services.sms_service import SMSStatus


class DummyCacheService:
    def __init__(self):
        self.store: dict[str, object] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: object, ttl: int | None = None):
        self.store[key] = value

    async def delete(self, key: str):
        self.store.pop(key, None)

    async def get_redis_client(self):
        return None

    def delete_pattern(self, _pattern: str):
        return None


class DummySMSService:
    def __init__(self, enabled: bool = True, status: SMSStatus = SMSStatus.SUCCESS):
        self.enabled = enabled
        self._status = status

    async def send_sms_with_status(self, _phone: str, _message: str):
        return None, self._status


class DummyAccountService:
    def __init__(self, *, has_future: bool = False, exception: Exception | None = None):
        self._has_future = has_future
        self._exception = exception

    def suspend_instructor_account(self, _user):
        if self._exception:
            raise self._exception
        return {"success": True, "message": "ok"}

    def deactivate_instructor_account(self, _user):
        if self._exception:
            raise self._exception
        return {"success": True, "message": "ok"}

    def reactivate_instructor_account(self, _user):
        if self._exception:
            raise self._exception
        return {"success": True, "message": "ok"}

    def has_future_bookings(self, _user):
        return self._has_future, []

    def get_account_status(self, _user):
        if self._exception:
            raise self._exception
        return {"account_status": "active", "can_login": True, "can_receive_bookings": True}


def _dummy_request():
    return SimpleNamespace(headers={}, client=None)


@pytest.mark.asyncio
async def test_suspend_account_for_student_forbidden(db, test_student):
    service = AccountLifecycleService(db, cache_service=DummyCacheService())
    with pytest.raises(HTTPException) as exc:
        await account_routes.suspend_account(
            request=_dummy_request(), current_user=test_student, account_service=service
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_suspend_and_reactivate_account(db, test_instructor_with_availability):
    service = AccountLifecycleService(db, cache_service=DummyCacheService())

    suspend = await account_routes.suspend_account(
        request=_dummy_request(),
        current_user=test_instructor_with_availability,
        account_service=service,
    )
    assert suspend.success is True

    test_instructor_with_availability.account_status = "suspended"
    db.commit()

    reactivated = await account_routes.reactivate_account(
        request=_dummy_request(),
        current_user=test_instructor_with_availability,
        account_service=service,
    )
    assert reactivated.success is True


@pytest.mark.asyncio
async def test_suspend_and_deactivate_business_rule_exceptions(test_instructor_with_availability):
    service = DummyAccountService(has_future=True, exception=BusinessRuleException("blocked"))
    with pytest.raises(HTTPException) as exc:
        await account_routes.suspend_account(
            request=_dummy_request(),
            current_user=test_instructor_with_availability, account_service=service
        )
    assert exc.value.status_code == 409

    service = DummyAccountService(has_future=False, exception=BusinessRuleException("blocked"))
    with pytest.raises(HTTPException) as exc:
        await account_routes.suspend_account(
            request=_dummy_request(),
            current_user=test_instructor_with_availability, account_service=service
        )
    assert exc.value.status_code == 400

    service = DummyAccountService(has_future=True, exception=BusinessRuleException("blocked"))
    with pytest.raises(HTTPException) as exc:
        await account_routes.deactivate_account(
            request=_dummy_request(),
            current_user=test_instructor_with_availability, account_service=service
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_reactivate_validation_error(test_instructor_with_availability):
    service = DummyAccountService(exception=ValidationException("bad"))
    with pytest.raises(HTTPException) as exc:
        await account_routes.reactivate_account(
            request=_dummy_request(),
            current_user=test_instructor_with_availability, account_service=service
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_suspend_audit_failure_does_not_break(db, test_instructor_with_availability, monkeypatch):
    service = AccountLifecycleService(db, cache_service=DummyCacheService())

    def _boom(*_args, **_kwargs):
        raise RuntimeError("audit failed")

    monkeypatch.setattr(account_routes.AuditService, "log_changes", _boom)

    response = await account_routes.suspend_account(
        request=_dummy_request(),
        current_user=test_instructor_with_availability,
        account_service=service,
    )
    assert response.success is True


@pytest.mark.asyncio
async def test_deactivate_audit_failure_does_not_break(db, test_instructor_with_availability, monkeypatch):
    service = AccountLifecycleService(db, cache_service=DummyCacheService())

    def _boom(*_args, **_kwargs):
        raise RuntimeError("audit failed")

    monkeypatch.setattr(account_routes.AuditService, "log_changes", _boom)

    response = await account_routes.deactivate_account(
        request=_dummy_request(),
        current_user=test_instructor_with_availability,
        account_service=service,
    )
    assert response.success is True


@pytest.mark.asyncio
async def test_reactivate_audit_failure_does_not_break(db, test_instructor_with_availability, monkeypatch):
    service = AccountLifecycleService(db, cache_service=DummyCacheService())

    test_instructor_with_availability.account_status = "suspended"
    db.commit()

    def _boom(*_args, **_kwargs):
        raise RuntimeError("audit failed")

    monkeypatch.setattr(account_routes.AuditService, "log_changes", _boom)

    response = await account_routes.reactivate_account(
        request=_dummy_request(),
        current_user=test_instructor_with_availability,
        account_service=service,
    )
    assert response.success is True


@pytest.mark.asyncio
async def test_account_status(db, test_instructor_with_availability):
    service = AccountLifecycleService(db, cache_service=DummyCacheService())
    status = await account_routes.check_account_status(
        current_user=test_instructor_with_availability, account_service=service
    )
    assert status.account_status is not None


@pytest.mark.asyncio
async def test_account_status_error(test_instructor_with_availability):
    service = DummyAccountService(exception=RuntimeError("boom"))
    with pytest.raises(HTTPException) as exc:
        await account_routes.check_account_status(
            current_user=test_instructor_with_availability, account_service=service
        )
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_phone_update_and_get(db, test_student):
    cache = DummyCacheService()
    test_student.phone = "+15551234567"
    test_student.phone_verified = False
    db.commit()

    res = await account_routes.get_phone_number(current_user=test_student)
    assert res.phone_number == "+15551234567"

    update = await account_routes.update_phone_number(
        account_routes.PhoneUpdateRequest(phone_number="+15559876543"),
        current_user=test_student,
        db=db,
        cache_service=cache,
    )
    assert update.phone_number == "+15559876543"

    update = await account_routes.update_phone_number(
        account_routes.PhoneUpdateRequest(phone_number="+15559876543"),
        current_user=test_student,
        db=db,
        cache_service=cache,
    )
    assert update.phone_number == "+15559876543"


@pytest.mark.asyncio
async def test_phone_update_invalid_format(db, test_student):
    cache = DummyCacheService()
    with pytest.raises(HTTPException) as exc:
        await account_routes.update_phone_number(
            account_routes.PhoneUpdateRequest(phone_number="5551234567"),
            current_user=test_student,
            db=db,
            cache_service=cache,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_phone_update_missing_user(db):
    cache = DummyCacheService()
    missing_user = account_routes.User(
        id="missing",
        email="missing@example.com",
        hashed_password="x",
        first_name="Missing",
        last_name="User",
        phone="+15551234567",
        zip_code="10001",
        is_active=True,
    )

    with pytest.raises(HTTPException) as exc:
        await account_routes.update_phone_number(
            account_routes.PhoneUpdateRequest(phone_number="+15551234567"),
            current_user=missing_user,
            db=db,
            cache_service=cache,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_phone_verification_send_and_confirm(db, test_student):
    cache = DummyCacheService()
    sms = DummySMSService(enabled=True, status=SMSStatus.SUCCESS)
    test_student.phone = "+15551234567"
    db.commit()

    sent = await account_routes.send_phone_verification(
        current_user=test_student,
        sms_service=sms,
        cache_service=cache,
    )
    assert sent.sent is True

    code_key = f"phone_verify:{test_student.id}"
    cached_code = cache.store[code_key]

    confirm = await account_routes.confirm_phone_verification(
        account_routes.PhoneVerifyConfirmRequest(code=str(cached_code)),
        current_user=test_student,
        db=db,
        cache_service=cache,
    )
    assert confirm.verified is True


@pytest.mark.asyncio
async def test_phone_verification_rate_limit_cache(db, test_student):
    cache = DummyCacheService()
    sms = DummySMSService(enabled=True, status=SMSStatus.SUCCESS)
    test_student.phone = "+15551234567"
    db.commit()

    rate_key = f"phone_verify_rate:{test_student.id}"
    cache.store[rate_key] = 3

    with pytest.raises(HTTPException) as exc:
        await account_routes.send_phone_verification(
            current_user=test_student,
            sms_service=sms,
            cache_service=cache,
        )
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_phone_verification_invalid_phone_format(db, test_student):
    cache = DummyCacheService()
    sms = DummySMSService(enabled=True, status=SMSStatus.SUCCESS)
    test_student.phone = "5551234567"
    db.commit()

    with pytest.raises(HTTPException) as exc:
        await account_routes.send_phone_verification(
            current_user=test_student,
            sms_service=sms,
            cache_service=cache,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_phone_verification_sms_failure(db, test_student):
    cache = DummyCacheService()
    sms = DummySMSService(enabled=True, status=SMSStatus.ERROR)
    test_student.phone = "+15551234567"
    db.commit()

    with pytest.raises(HTTPException) as exc:
        await account_routes.send_phone_verification(
            current_user=test_student,
            sms_service=sms,
            cache_service=cache,
        )
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_phone_verification_confirm_attempts_limit(db, test_student):
    cache = DummyCacheService()
    test_student.phone = "+15551234567"
    db.commit()

    attempts_key = f"phone_confirm_attempts:{test_student.id}"
    cache.store[attempts_key] = 5

    with pytest.raises(HTTPException) as exc:
        await account_routes.confirm_phone_verification(
            account_routes.PhoneVerifyConfirmRequest(code="000000"),
            current_user=test_student,
            db=db,
            cache_service=cache,
        )
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_phone_verification_errors(db, test_student):
    cache = DummyCacheService()
    test_student.phone = None
    db.commit()

    with pytest.raises(HTTPException):
        await account_routes.send_phone_verification(
            current_user=test_student,
            sms_service=DummySMSService(enabled=True),
            cache_service=cache,
        )

    test_student.phone = "+15551234567"
    db.commit()

    with pytest.raises(HTTPException) as exc:
        await account_routes.send_phone_verification(
            current_user=test_student,
            sms_service=DummySMSService(enabled=False),
            cache_service=cache,
        )
    assert exc.value.status_code == 503

    cache.store[f"phone_verify:{test_student.id}"] = "123456"
    with pytest.raises(HTTPException) as exc:
        await account_routes.confirm_phone_verification(
            account_routes.PhoneVerifyConfirmRequest(code="000000"),
            current_user=test_student,
            db=db,
            cache_service=cache,
        )
    assert exc.value.status_code == 400
