"""Additional branch coverage tests for InstructorService."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.core.enums import RoleName
from app.core.exceptions import BusinessRuleException, NotFoundException, ServiceException
from app.services.instructor_service import InstructorService


@contextmanager
def _tx_ctx():
    yield None


def _service() -> InstructorService:
    service = InstructorService.__new__(InstructorService)
    service.db = MagicMock()
    service.transaction = MagicMock(return_value=_tx_ctx())
    service.cache_service = MagicMock()
    service.profile_repository = MagicMock()
    service.service_repository = MagicMock()
    return service


def test_delete_instructor_profile_raises_when_missing_profile():
    service = _service()
    service.profile_repository.find_one_by.return_value = None

    with pytest.raises(NotFoundException):
        service.delete_instructor_profile("user-1")


def test_delete_instructor_profile_cleans_services_and_handles_cleanup_error():
    service = _service()
    profile = SimpleNamespace(id="profile-1")
    active_service = SimpleNamespace(id="svc-active", is_active=True)
    inactive_service = SimpleNamespace(id="svc-inactive", is_active=False)

    service.profile_repository.find_one_by.return_value = profile
    service.service_repository.find_by.return_value = [active_service, inactive_service]

    with patch("app.services.permission_service.PermissionService") as permission_cls:
        permission = permission_cls.return_value
        with patch(
            "app.services.instructor_service.invalidate_on_instructor_profile_change"
        ) as invalidate_search:
            with patch(
                "app.services.availability_service.AvailabilityService",
                side_effect=RuntimeError("cleanup-boom"),
            ):
                service.delete_instructor_profile("user-1")

    service.service_repository.update.assert_called_once_with("svc-active", is_active=False)
    service.profile_repository.delete.assert_called_once_with("profile-1")
    permission.remove_role.assert_called_once_with("user-1", RoleName.INSTRUCTOR)
    permission.assign_role.assert_called_once_with("user-1", RoleName.STUDENT)
    service.cache_service.delete.assert_called_with("instructor:public:user-1")
    service.cache_service.invalidate_instructor_availability.assert_called_once_with("user-1")
    invalidate_search.assert_called_once_with("user-1")


def test_go_live_missing_prerequisites_uses_default_connect_status_when_profile_has_no_id():
    service = _service()
    profile = SimpleNamespace(
        id=None,
        user_id="user-1",
        skills_configured=False,
        identity_verified_at=None,
        bgc_status="pending",
    )
    service.profile_repository.find_one_by.return_value = profile

    with pytest.raises(BusinessRuleException) as exc_info:
        service.go_live("user-1")

    missing = set(exc_info.value.details.get("missing", []))
    assert {"skills", "identity", "stripe_connect", "background_check"}.issubset(missing)


def test_go_live_updates_existing_onboarding_profile_and_returns_profile():
    service = _service()
    profile = SimpleNamespace(
        id="profile-1",
        user_id="user-1",
        skills_configured=True,
        identity_verified_at=datetime.now(timezone.utc),
        bgc_status="passed",
        onboarding_completed_at=datetime.now(timezone.utc),
    )
    service.profile_repository.find_one_by.return_value = profile
    service.profile_repository.update.return_value = profile

    with patch("app.services.instructor_service.ConfigService"), patch(
        "app.services.instructor_service.PricingService"
    ), patch("app.services.instructor_service.StripeService") as stripe_cls, patch(
        "app.services.instructor_service.InstructorLifecycleService"
    ) as lifecycle_cls:
        stripe_cls.return_value.check_account_status.return_value = {
            "has_account": True,
            "onboarding_completed": True,
        }

        result = service.go_live("user-1")

    assert result is profile
    service.profile_repository.update.assert_called_once_with("profile-1", is_live=True)
    lifecycle_cls.return_value.record_went_live.assert_called_once_with("user-1")


def test_go_live_raises_service_exception_when_update_returns_none():
    service = _service()
    profile = SimpleNamespace(
        id="profile-1",
        user_id="user-1",
        skills_configured=True,
        identity_verified_at=datetime.now(timezone.utc),
        bgc_status="passed",
        onboarding_completed_at=None,
    )
    service.profile_repository.find_one_by.return_value = profile
    service.profile_repository.update.return_value = None

    with patch("app.services.instructor_service.ConfigService"), patch(
        "app.services.instructor_service.PricingService"
    ), patch("app.services.instructor_service.StripeService") as stripe_cls, patch(
        "app.services.instructor_service.InstructorLifecycleService"
    ):
        stripe_cls.return_value.check_account_status.return_value = {
            "has_account": True,
            "onboarding_completed": True,
        }

        with pytest.raises(ServiceException):
            service.go_live("user-1")
