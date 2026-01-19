from __future__ import annotations

from types import SimpleNamespace

from app.services.email_config import EmailConfigService


def test_email_config_service_senders() -> None:
    service = EmailConfigService(SimpleNamespace())

    assert "Alerts" in service.get_monitoring_sender()
    assert "Bookings" in service.get_booking_sender()
    assert "Security" in service.get_security_sender()
    assert service.get_transactional_sender().endswith("<hello@instainstru.com>")


def test_email_config_service_default_sender() -> None:
    service = EmailConfigService(SimpleNamespace())

    assert service.get_sender("missing") == service.get_sender("default")
