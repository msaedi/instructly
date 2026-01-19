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
