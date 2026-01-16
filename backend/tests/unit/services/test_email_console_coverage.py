from __future__ import annotations

from app.services.email_console import ConsoleEmailService


def test_console_email_service_send_email() -> None:
    service = ConsoleEmailService()
    assert service.send_email("user@example.com", "Hello", "<p>Hi</p>", tags=["test"])


def test_console_email_service_send_template() -> None:
    service = ConsoleEmailService()
    assert service.send_template(
        "user@example.com",
        "welcome",
        {"name": "Ada"},
        tags=["welcome"],
    )
