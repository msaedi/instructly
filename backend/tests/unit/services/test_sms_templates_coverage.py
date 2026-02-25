"""Tests for app/services/sms_templates.py — coverage gaps L98-99."""
from __future__ import annotations

import pytest

from app.services.sms_templates import (
    BOOKING_CONFIRMED_INSTRUCTOR,
    BOOKING_CONFIRMED_STUDENT,
    BOOKING_NEW_MESSAGE,
    PAYMENT_FAILED,
    SMSTemplate,
    render_sms,
)


@pytest.mark.unit
class TestRenderSmsCoverage:
    """Cover L98-99: KeyError path in render_sms."""

    def test_missing_template_variable_raises(self) -> None:
        """L98-99: missing kwarg triggers KeyError → ValueError."""
        with pytest.raises(ValueError, match="Missing template variable"):
            render_sms(BOOKING_CONFIRMED_INSTRUCTOR, student_name="Alice")
            # Missing: service_name, date, time

    def test_missing_single_variable(self) -> None:
        with pytest.raises(ValueError, match="Missing template variable"):
            render_sms(
                BOOKING_CONFIRMED_INSTRUCTOR,
                student_name="Alice",
                service_name="Piano",
                date="2025-07-01",
                # Missing: time
            )

    def test_render_success(self) -> None:
        result = render_sms(
            BOOKING_CONFIRMED_INSTRUCTOR,
            student_name="Alice",
            service_name="Piano",
            date="2025-07-01",
            time="10:00 AM",
        )
        assert "Alice" in result
        assert "Piano" in result
        assert "2025-07-01" in result
        assert "10:00 AM" in result

    def test_render_student_template(self) -> None:
        result = render_sms(
            BOOKING_CONFIRMED_STUDENT,
            service_name="Guitar",
            instructor_name="Bob",
            date="2025-08-01",
            time="2:00 PM",
        )
        assert "Guitar" in result
        assert "Bob" in result

    def test_render_new_message(self) -> None:
        result = render_sms(
            BOOKING_NEW_MESSAGE,
            sender_name="Carol",
            service_name="Violin",
            message_preview="Hey, can we...",
        )
        assert "Carol" in result
        assert "Hey, can we..." in result

    def test_render_payment_failed(self) -> None:
        result = render_sms(
            PAYMENT_FAILED,
            service_name="Drums",
            instructor_name="Dave",
            date="2025-09-01",
            payment_url="https://example.com/pay",
        )
        assert "https://example.com/pay" in result

    def test_custom_template(self) -> None:
        tpl = SMSTemplate(category="test", template="Hello {name}!")
        result = render_sms(tpl, name="World")
        assert result == "Hello World!"

    def test_custom_template_missing_key(self) -> None:
        tpl = SMSTemplate(category="test", template="Hello {name}! Your code is {code}.")
        with pytest.raises(ValueError, match="Missing template variable"):
            render_sms(tpl, name="World")

    def test_no_kwargs_raises(self) -> None:
        """All templates require at least one variable."""
        with pytest.raises(ValueError, match="Missing template variable"):
            render_sms(BOOKING_CONFIRMED_INSTRUCTOR)
