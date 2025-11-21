from app.core.config import settings
from app.services.adverse_action_email_templates import (
    build_final_adverse_email,
    build_pre_adverse_email,
)


def test_pre_adverse_template_contains_required_content():
    template = build_pre_adverse_email(business_days=5)

    assert "pre-adverse action" in template.subject.lower()
    assert settings.checkr_applicant_portal_url in template.html
    assert settings.checkr_dispute_contact_url in template.html
    assert settings.ftc_summary_of_rights_url in template.html
    lower_html = template.html.lower()
    assert "summary of your rights under the fair credit reporting act" in lower_html
    assert "5 business days" in template.html
    assert "considering whether to move forward" in lower_html
    assert "no final decision has been made" in lower_html
    assert "pause any decision" in template.text.lower()
    assert "summary of your rights under the fair credit reporting act" in template.text.lower()


def test_final_adverse_template_contains_required_content():
    template = build_final_adverse_email()

    assert "final adverse action" in template.subject.lower()
    assert "have taken adverse action" in template.html.lower()
    assert "right to dispute" in template.html.lower()
    assert "free copy" in template.html.lower()
    assert settings.checkr_dispute_contact_url in template.html
    assert settings.ftc_summary_of_rights_url in template.html
    assert settings.checkr_applicant_portal_url in template.html
    assert "summary of your rights under the fair credit reporting act" in template.html.lower()
    assert "reinvestigation" in template.html.lower()

    assert "right to dispute" in template.text.lower()
    assert "summary of your rights under the fair credit reporting act" in template.text.lower()
