import pytest

from app.services.template_registry import TemplateRegistry
from app.services.template_service import TemplateService


@pytest.fixture
def template_service(db):
    # Use real TemplateService; it does not require DB
    return TemplateService(db=None, cache=None)


def test_referral_invite_template_renders(template_service):
    html = template_service.render_template(
        TemplateRegistry.REFERRALS_INVITE,
        context={"inviter_name": "Emma", "referral_link": "https://instainstru.com/ref/ABC123"},
    )
    assert "Emma" in html
    assert "https://instainstru.com/ref/ABC123" in html


def test_password_reset_templates_render(template_service):
    html_reset = template_service.render_template(
        TemplateRegistry.AUTH_PASSWORD_RESET,
        context={"reset_url": "https://instainstru.com/reset/XYZ", "user_name": "Alex"},
    )
    assert "Alex" in html_reset
    assert "reset/XYZ" in html_reset

    html_confirm = template_service.render_template(
        TemplateRegistry.AUTH_PASSWORD_RESET_CONFIRMATION,
        context={"user_name": "Alex"},
    )
    assert "Password" in html_confirm
