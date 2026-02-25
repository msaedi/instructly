from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api.dependencies import services as dep_services
from app.services import template_service as template_module


def _clear_cache_singletons() -> None:
    dep_services.get_cache_service_singleton.cache_clear()
    dep_services.get_cache_service_sync_singleton.cache_clear()


def test_cache_service_singletons_reuse_instances() -> None:
    _clear_cache_singletons()
    first = dep_services.get_cache_service_singleton()
    second = dep_services.get_cache_service_singleton()

    assert first is second

    sync_first = dep_services.get_cache_service_sync_singleton()
    sync_second = dep_services.get_cache_service_sync_singleton()

    assert sync_first is sync_second
    assert sync_first._cache_service is first


def test_get_notification_service_uses_injected_services(monkeypatch) -> None:
    class DummyTemplate:
        def __init__(self, db, cache):
            self.db = db
            self.cache = cache

    class DummyNotification:
        def __init__(self, db, cache, template_service, email_service, sms_service=None):
            self.db = db
            self.cache = cache
            self.template_service = template_service
            self.email_service = email_service
            self.sms_service = sms_service

    monkeypatch.setattr(template_module, "TemplateService", DummyTemplate)
    monkeypatch.setattr(dep_services, "NotificationService", DummyNotification)

    db = SimpleNamespace()
    cache = SimpleNamespace()
    email = SimpleNamespace()
    sms = SimpleNamespace()

    service = dep_services.get_notification_service(
        db=db, cache=cache, email_service=email, sms_service=sms
    )

    assert isinstance(service, DummyNotification)
    assert service.db is db
    assert service.cache is cache
    assert isinstance(service.template_service, DummyTemplate)
    assert service.email_service is email
    assert service.sms_service is sms


def test_get_booking_service_injects_dependencies(monkeypatch) -> None:
    created = {}

    class DummyBooking:
        def __init__(
            self, db, notification_service, repository=None, conflict_checker_repository=None, cache_service=None
        ):
            created["db"] = db
            created["notification"] = notification_service
            created["cache"] = cache_service

    monkeypatch.setattr(dep_services, "BookingService", DummyBooking)

    db = SimpleNamespace()
    notification = SimpleNamespace()
    cache = SimpleNamespace()

    dep_services.get_booking_service(db=db, notification_service=notification, cache_service=cache)

    assert created["db"] is db
    assert created["notification"] is notification
    assert created["cache"] is cache


def test_get_background_check_service_uses_fake_client(monkeypatch) -> None:
    class DummyRepo:
        def __init__(self, db):
            self.db = db

    class DummyFakeClient:
        pass

    monkeypatch.setattr(dep_services, "InstructorProfileRepository", DummyRepo)
    monkeypatch.setattr(dep_services, "FakeCheckrClient", DummyFakeClient)
    monkeypatch.setattr(dep_services.settings, "checkr_fake", True, raising=False)
    monkeypatch.setattr(dep_services.settings, "checkr_env", "sandbox", raising=False)
    monkeypatch.setattr(dep_services.settings, "checkr_package", "pkg", raising=False)

    service = dep_services.get_background_check_service(db=SimpleNamespace())

    assert isinstance(service.client, DummyFakeClient)
    assert service.is_fake_client is True
    assert service.config_error is None


def test_get_background_check_service_falls_back_on_config_error(monkeypatch) -> None:
    class DummyRepo:
        def __init__(self, db):
            self.db = db

    class DummyFakeClient:
        pass

    def _raise(*_args, **_kwargs):
        raise ValueError("missing api key")

    monkeypatch.setattr(dep_services, "InstructorProfileRepository", DummyRepo)
    monkeypatch.setattr(dep_services, "CheckrClient", _raise)
    monkeypatch.setattr(dep_services, "FakeCheckrClient", DummyFakeClient)
    monkeypatch.setattr(dep_services.settings, "checkr_fake", False, raising=False)
    monkeypatch.setattr(dep_services.settings, "checkr_env", "sandbox", raising=False)
    monkeypatch.setattr(dep_services.settings, "checkr_package", "pkg", raising=False)
    monkeypatch.setenv("SITE_MODE", "local")

    service = dep_services.get_background_check_service(db=SimpleNamespace())

    assert isinstance(service.client, DummyFakeClient)
    assert service.is_fake_client is True
    assert service.config_error == "missing api key"


def test_get_background_check_service_raises_in_prod(monkeypatch) -> None:
    class DummyRepo:
        def __init__(self, db):
            self.db = db

    def _raise(*_args, **_kwargs):
        raise ValueError("missing api key")

    monkeypatch.setattr(dep_services, "InstructorProfileRepository", DummyRepo)
    monkeypatch.setattr(dep_services, "CheckrClient", _raise)
    monkeypatch.setattr(dep_services.settings, "checkr_fake", False, raising=False)
    monkeypatch.setattr(dep_services.settings, "checkr_env", "sandbox", raising=False)
    monkeypatch.setattr(dep_services.settings, "checkr_package", "pkg", raising=False)
    monkeypatch.setenv("SITE_MODE", "prod")

    with pytest.raises(ValueError):
        dep_services.get_background_check_service(db=SimpleNamespace())


def test_get_week_operation_service_wires_dependencies(monkeypatch) -> None:
    created = {}

    class DummyWeekService:
        def __init__(self, db, availability_service, conflict_checker, cache_service):
            created["db"] = db
            created["availability"] = availability_service
            created["conflict"] = conflict_checker
            created["cache"] = cache_service

    monkeypatch.setattr(dep_services, "WeekOperationService", DummyWeekService)

    db = SimpleNamespace()
    availability = SimpleNamespace()
    conflict = SimpleNamespace()
    cache = SimpleNamespace()

    dep_services.get_week_operation_service(
        db=db,
        availability_service=availability,
        conflict_checker=conflict,
        cache_service=cache,
    )

    assert created == {
        "db": db,
        "availability": availability,
        "conflict": conflict,
        "cache": cache,
    }


# ──────────────────────────────────────────────────────────────
# Additional coverage: service factory functions (L155,165,170,177,182,281,298,416)
# ──────────────────────────────────────────────────────────────

def test_get_booking_detail_service(monkeypatch) -> None:
    """L155: BookingDetailService(db) constructor."""
    created = {}

    class DummyService:
        def __init__(self, db):
            created["db"] = db

    monkeypatch.setattr(dep_services, "BookingDetailService", DummyService)
    db = SimpleNamespace()
    dep_services.get_booking_detail_service(db=db)
    assert created["db"] is db


def test_get_refund_service(monkeypatch) -> None:
    """L155: RefundService(db) constructor."""
    created = {}

    class DummyService:
        def __init__(self, db):
            created["db"] = db

    monkeypatch.setattr(dep_services, "RefundService", DummyService)
    db = SimpleNamespace()
    dep_services.get_refund_service(db=db)
    assert created["db"] is db


def test_get_booking_admin_service(monkeypatch) -> None:
    """L165: BookingAdminService(db) constructor."""
    created = {}

    class DummyService:
        def __init__(self, db):
            created["db"] = db

    monkeypatch.setattr(dep_services, "BookingAdminService", DummyService)
    db = SimpleNamespace()
    dep_services.get_booking_admin_service(db=db)
    assert created["db"] is db


def test_get_instructor_admin_service(monkeypatch) -> None:
    """L165: InstructorAdminService(db) constructor."""
    created = {}

    class DummyService:
        def __init__(self, db):
            created["db"] = db

    monkeypatch.setattr(dep_services, "InstructorAdminService", DummyService)
    db = SimpleNamespace()
    dep_services.get_instructor_admin_service(db=db)
    assert created["db"] is db


def test_get_student_admin_service(monkeypatch) -> None:
    """L170: StudentAdminService(db) constructor."""
    created = {}

    class DummyService:
        def __init__(self, db):
            created["db"] = db

    monkeypatch.setattr(dep_services, "StudentAdminService", DummyService)
    db = SimpleNamespace()
    dep_services.get_student_admin_service(db=db)
    assert created["db"] is db


def test_get_communication_admin_service(monkeypatch) -> None:
    """L177: CommunicationAdminService(db) constructor."""
    created = {}

    class DummyService:
        def __init__(self, db):
            created["db"] = db

    monkeypatch.setattr(dep_services, "CommunicationAdminService", DummyService)
    db = SimpleNamespace()
    dep_services.get_communication_admin_service(db=db)
    assert created["db"] is db


def test_get_platform_analytics_service(monkeypatch) -> None:
    """L182: PlatformAnalyticsService(db) constructor."""
    created = {}

    class DummyService:
        def __init__(self, db):
            created["db"] = db

    monkeypatch.setattr(dep_services, "PlatformAnalyticsService", DummyService)
    db = SimpleNamespace()
    dep_services.get_platform_analytics_service(db=db)
    assert created["db"] is db


def test_get_funnel_analytics_service(monkeypatch) -> None:
    """L182: FunnelAnalyticsService(db) constructor."""
    created = {}

    class DummyService:
        def __init__(self, db):
            created["db"] = db

    monkeypatch.setattr(dep_services, "FunnelAnalyticsService", DummyService)
    db = SimpleNamespace()
    dep_services.get_funnel_analytics_service(db=db)
    assert created["db"] is db


def test_get_referral_service(monkeypatch) -> None:
    """L281: ReferralService(db) constructor."""
    created = {}

    class DummyService:
        def __init__(self, db):
            created["db"] = db

    monkeypatch.setattr(dep_services, "ReferralService", DummyService)
    db = SimpleNamespace()
    dep_services.get_referral_service(db=db)
    assert created["db"] is db


def test_get_wallet_service(monkeypatch) -> None:
    """L281: WalletService(db) constructor."""
    created = {}

    class DummyService:
        def __init__(self, db):
            created["db"] = db

    monkeypatch.setattr(dep_services, "WalletService", DummyService)
    db = SimpleNamespace()
    dep_services.get_wallet_service(db=db)
    assert created["db"] is db


def test_get_background_check_workflow_service(monkeypatch) -> None:
    """L298: BackgroundCheckWorkflowService(repo) constructor."""
    created = {}

    class DummyService:
        def __init__(self, repo):
            created["repo"] = repo

    monkeypatch.setattr(dep_services, "BackgroundCheckWorkflowService", DummyService)
    repo = SimpleNamespace()
    dep_services.get_background_check_workflow_service(repo=repo)
    assert created["repo"] is repo


def test_get_referral_checkout_service(monkeypatch) -> None:
    """L298: ReferralCheckoutService(db, wallet_service) constructor."""
    created = {}

    class DummyService:
        def __init__(self, db, wallet_service):
            created["db"] = db
            created["wallet"] = wallet_service

    monkeypatch.setattr(dep_services, "ReferralCheckoutService", DummyService)
    db = SimpleNamespace()
    wallet = SimpleNamespace()
    dep_services.get_referral_checkout_service(db=db, wallet_service=wallet)
    assert created["db"] is db
    assert created["wallet"] is wallet


def test_get_two_factor_auth_service(monkeypatch) -> None:
    """L416: TwoFactorAuthService(db) constructor."""
    created = {}

    class DummyService:
        def __init__(self, db):
            created["db"] = db

    monkeypatch.setattr(dep_services, "TwoFactorAuthService", DummyService)
    db = SimpleNamespace()
    dep_services.get_two_factor_auth_service(db=db)
    assert created["db"] is db


def test_get_auth_service(monkeypatch) -> None:
    """L416: AuthService(db) constructor."""
    created = {}

    class DummyService:
        def __init__(self, db):
            created["db"] = db

    monkeypatch.setattr(dep_services, "AuthService", DummyService)
    db = SimpleNamespace()
    dep_services.get_auth_service(db=db)
    assert created["db"] is db


def test_get_password_reset_service(monkeypatch) -> None:
    """PasswordResetService(db, email_service) constructor."""
    created = {}

    class DummyService:
        def __init__(self, db, email_service=None):
            created["db"] = db
            created["email"] = email_service

    monkeypatch.setattr(dep_services, "PasswordResetService", DummyService)
    db = SimpleNamespace()
    email = SimpleNamespace()
    dep_services.get_password_reset_service(db=db, email_service=email)
    assert created["db"] is db
    assert created["email"] is email


def test_get_presentation_service(monkeypatch) -> None:
    """PresentationService(db) constructor."""
    created = {}

    class DummyService:
        def __init__(self, db):
            created["db"] = db

    monkeypatch.setattr(dep_services, "PresentationService", DummyService)
    db = SimpleNamespace()
    dep_services.get_presentation_service(db=db)
    assert created["db"] is db


def test_get_pricing_service(monkeypatch) -> None:
    """PricingService(db) constructor."""
    created = {}

    class DummyService:
        def __init__(self, db):
            created["db"] = db

    monkeypatch.setattr(dep_services, "PricingService", DummyService)
    db = SimpleNamespace()
    dep_services.get_pricing_service(db=db)
    assert created["db"] is db


def test_get_catalog_browse_service(monkeypatch) -> None:
    """CatalogBrowseService(db) constructor."""
    created = {}

    class DummyService:
        def __init__(self, db):
            created["db"] = db

    monkeypatch.setattr(dep_services, "CatalogBrowseService", DummyService)
    db = SimpleNamespace()
    dep_services.get_catalog_browse_service(db=db)
    assert created["db"] is db


def test_get_instructor_service(monkeypatch) -> None:
    """InstructorService(db, cache_service) constructor."""
    created = {}

    class DummyService:
        def __init__(self, db, cache_service):
            created["db"] = db
            created["cache"] = cache_service

    monkeypatch.setattr(dep_services, "InstructorService", DummyService)
    # Also patch the local import inside get_instructor_service
    import app.services.instructor_service as instr_mod
    monkeypatch.setattr(instr_mod, "InstructorService", DummyService)
    db = SimpleNamespace()
    cache = SimpleNamespace()
    dep_services.get_instructor_service(db=db, cache_service=cache)
    assert created["db"] is db
    assert created["cache"] is cache


def test_get_favorites_service(monkeypatch) -> None:
    """FavoritesService(db, cache_service) constructor."""
    created = {}

    class DummyService:
        def __init__(self, db, cache_service=None):
            created["db"] = db
            created["cache"] = cache_service

    monkeypatch.setattr(dep_services, "FavoritesService", DummyService)
    db = SimpleNamespace()
    cache = SimpleNamespace()
    dep_services.get_favorites_service(db=db, cache_service=cache)
    assert created["db"] is db
    assert created["cache"] is cache


def test_get_availability_service(monkeypatch) -> None:
    """AvailabilityService(db, cache_service) constructor."""
    created = {}

    class DummyService:
        def __init__(self, db, cache_service):
            created["db"] = db
            created["cache"] = cache_service

    monkeypatch.setattr(dep_services, "AvailabilityService", DummyService)
    db = SimpleNamespace()
    cache = SimpleNamespace()
    dep_services.get_availability_service(db=db, cache_service=cache)
    assert created["db"] is db
    assert created["cache"] is cache


def test_get_conflict_checker(monkeypatch) -> None:
    """ConflictChecker(db) constructor."""
    created = {}

    class DummyService:
        def __init__(self, db):
            created["db"] = db

    monkeypatch.setattr(dep_services, "ConflictChecker", DummyService)
    db = SimpleNamespace()
    dep_services.get_conflict_checker(db=db)
    assert created["db"] is db


def test_get_bulk_operation_service(monkeypatch) -> None:
    """BulkOperationService(db, slot_manager, conflict_checker, cache_service) constructor."""
    created = {}

    class DummyService:
        def __init__(self, db, slot_manager=None, conflict_checker=None, cache_service=None):
            created["db"] = db
            created["slot_manager"] = slot_manager
            created["conflict"] = conflict_checker
            created["cache"] = cache_service

    monkeypatch.setattr(dep_services, "BulkOperationService", DummyService)
    db = SimpleNamespace()
    conflict = SimpleNamespace()
    cache = SimpleNamespace()
    dep_services.get_bulk_operation_service(db=db, conflict_checker=conflict, cache_service=cache)
    assert created["db"] is db
    assert created["slot_manager"] is None
    assert created["conflict"] is conflict
    assert created["cache"] is cache


def test_get_account_lifecycle_service(monkeypatch) -> None:
    """AccountLifecycleService(db, cache_service) constructor."""
    created = {}

    class DummyService:
        def __init__(self, db, cache_service):
            created["db"] = db
            created["cache"] = cache_service

    monkeypatch.setattr(dep_services, "AccountLifecycleService", DummyService)
    db = SimpleNamespace()
    cache = SimpleNamespace()
    dep_services.get_account_lifecycle_service(db=db, cache_service=cache)
    assert created["db"] is db
    assert created["cache"] is cache


def test_get_email_service(monkeypatch) -> None:
    """EmailService(db, cache) constructor."""
    created = {}

    class DummyService:
        def __init__(self, db, cache):
            created["db"] = db
            created["cache"] = cache

    monkeypatch.setattr(dep_services, "EmailService", DummyService)
    db = SimpleNamespace()
    cache = SimpleNamespace()
    dep_services.get_email_service(db=db, cache=cache)
    assert created["db"] is db
    assert created["cache"] is cache


def test_get_sms_service(monkeypatch) -> None:
    """SMSService(cache) constructor."""
    created = {}

    class DummyService:
        def __init__(self, cache):
            created["cache"] = cache

    monkeypatch.setattr(dep_services, "SMSService", DummyService)
    cache = SimpleNamespace()
    dep_services.get_sms_service(cache=cache)
    assert created["cache"] is cache


def test_get_cache_service_dep() -> None:
    """get_cache_service_dep returns the singleton."""
    _clear_cache_singletons()
    result = dep_services.get_cache_service_dep()
    assert result is dep_services.get_cache_service_singleton()


def test_get_cache_service_sync_dep() -> None:
    """get_cache_service_sync_dep returns the sync singleton."""
    _clear_cache_singletons()
    result = dep_services.get_cache_service_sync_dep()
    assert result is dep_services.get_cache_service_sync_singleton()
