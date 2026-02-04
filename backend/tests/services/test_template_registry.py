from __future__ import annotations

from app.services.template_registry import TemplateRegistry, get_default_sender_key


def test_template_registry_defaults_and_values():
    assert TemplateRegistry.BOOKING_COMPLETED_STUDENT.value.endswith("completed_student.html")
    assert TemplateRegistry.BOOKING_COMPLETED_INSTRUCTOR.value.endswith("completed_instructor.html")
    assert TemplateRegistry.REVIEW_NEW_REVIEW.value.endswith("new_review.html")
    assert TemplateRegistry.REVIEW_RESPONSE.value.endswith("review_response.html")
    assert TemplateRegistry.BGC_FINAL_ADVERSE.value.endswith("final_adverse.jinja")
    assert TemplateRegistry.BGC_EXPIRY_RECHECK.value.endswith("expiry_recheck.jinja")

    assert get_default_sender_key(TemplateRegistry.BOOKING_COMPLETED_STUDENT) == "bookings"
    assert get_default_sender_key(TemplateRegistry.REVIEW_NEW_REVIEW) == "bookings"
    assert get_default_sender_key(TemplateRegistry.BGC_FINAL_ADVERSE) == "trust"
