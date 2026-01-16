from __future__ import annotations

from types import SimpleNamespace

from app.services import dependencies as deps


def test_get_cache_service_sync_adapter(monkeypatch) -> None:
    fake_cache = SimpleNamespace(key_builder=SimpleNamespace())
    monkeypatch.setattr(deps, "get_cache_service", lambda _db: fake_cache)

    adapter = deps.get_cache_service_sync(db=SimpleNamespace())

    assert adapter._cache_service is fake_cache


def test_get_template_service(monkeypatch) -> None:
    created = {}

    class DummyTemplate:
        def __init__(self, db, cache):
            created["db"] = db
            created["cache"] = cache

    monkeypatch.setattr(deps, "TemplateService", DummyTemplate)

    db = SimpleNamespace()
    cache = SimpleNamespace()
    deps.get_template_service(db=db, cache=cache)

    assert created["db"] is db
    assert created["cache"] is cache


def test_get_notification_service(monkeypatch) -> None:
    created = {}

    class DummyNotification:
        def __init__(self, db, cache, template_service):
            created["db"] = db
            created["cache"] = cache
            created["template"] = template_service

    monkeypatch.setattr(deps, "NotificationService", DummyNotification)

    db = SimpleNamespace()
    cache = SimpleNamespace()
    template = SimpleNamespace()

    deps.get_notification_service(db=db, cache=cache, template_service=template)

    assert created == {"db": db, "cache": cache, "template": template}


def test_get_booking_service(monkeypatch) -> None:
    created = {}

    class DummyBooking:
        def __init__(self, db, notification_service, cache_service=None):
            created["db"] = db
            created["notification"] = notification_service
            created["cache"] = cache_service

    monkeypatch.setattr(deps, "BookingService", DummyBooking)

    db = SimpleNamespace()
    notification = SimpleNamespace()
    cache = SimpleNamespace()

    deps.get_booking_service(db=db, cache=cache, notification_service=notification)

    assert created == {"db": db, "notification": notification, "cache": cache}


def test_get_account_lifecycle_service(monkeypatch) -> None:
    created = {}

    class DummyLifecycle:
        def __init__(self, db, cache):
            created["db"] = db
            created["cache"] = cache

    monkeypatch.setattr(deps, "AccountLifecycleService", DummyLifecycle)

    db = SimpleNamespace()
    cache = SimpleNamespace()

    deps.get_account_lifecycle_service(db=db, cache=cache)

    assert created == {"db": db, "cache": cache}


def test_get_personal_asset_service(monkeypatch) -> None:
    created = {}

    class DummyPersonal:
        def __init__(self, db):
            created["db"] = db

    monkeypatch.setattr(deps, "PersonalAssetService", DummyPersonal)

    db = SimpleNamespace()
    deps.get_personal_asset_service(db=db)

    assert created == {"db": db}


def test_get_email_service_console_provider(monkeypatch) -> None:
    monkeypatch.setattr(deps.settings, "email_provider", "console", raising=False)
    monkeypatch.setattr(deps.settings, "resend_api_key", "", raising=False)

    class DummyConsole:
        pass

    monkeypatch.setattr(deps, "ConsoleEmailService", DummyConsole)

    service = deps.get_email_service(db=SimpleNamespace(), cache=SimpleNamespace())

    assert isinstance(service, DummyConsole)


def test_get_email_service_missing_key(monkeypatch) -> None:
    monkeypatch.setattr(deps.settings, "email_provider", "resend", raising=False)
    monkeypatch.setattr(deps.settings, "resend_api_key", "", raising=False)
    monkeypatch.setenv("SITE_MODE", "prod")
    monkeypatch.delenv("CI", raising=False)

    class DummyConsole:
        pass

    monkeypatch.setattr(deps, "ConsoleEmailService", DummyConsole)

    service = deps.get_email_service(db=SimpleNamespace(), cache=SimpleNamespace())

    assert isinstance(service, DummyConsole)


def test_get_email_service_real_provider(monkeypatch) -> None:
    monkeypatch.setattr(deps.settings, "email_provider", "resend", raising=False)
    monkeypatch.setattr(deps.settings, "resend_api_key", "key", raising=False)
    monkeypatch.setenv("SITE_MODE", "prod")
    monkeypatch.delenv("CI", raising=False)

    class DummyEmail:
        def __init__(self, db, cache):
            self.db = db
            self.cache = cache

    monkeypatch.setattr(deps, "EmailService", DummyEmail)

    db = SimpleNamespace()
    cache = SimpleNamespace()

    service = deps.get_email_service(db=db, cache=cache)

    assert isinstance(service, DummyEmail)
    assert service.db is db
    assert service.cache is cache
