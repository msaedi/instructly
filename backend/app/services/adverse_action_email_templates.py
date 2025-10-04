"""Email templates for adverse-action notifications."""

from __future__ import annotations

from dataclasses import dataclass

from ..core.config import settings
from ..core.constants import BRAND_NAME


@dataclass
class AdverseEmailTemplate:
    subject: str
    html: str
    text: str


def build_pre_adverse_email(*, business_days: int = 5) -> AdverseEmailTemplate:
    """Return the subject and bodies for the pre-adverse action notice."""

    portal_url = settings.checkr_applicant_portal_url
    dispute_url = settings.checkr_dispute_contact_url
    summary_url = settings.ftc_summary_of_rights_url
    support_email = settings.bgc_support_email

    subject = f"{BRAND_NAME}: Pre-adverse action notice"

    html = f"""
    <p>We are contacting you about your recent background report for {BRAND_NAME}. Based on information in the report, adverse action may be taken. This message is a pre-adverse action notice.</p>
    <p>You can review your complete background report at <a href='{portal_url}'>{portal_url}</a>.</p>
    <p>If you believe any information is inaccurate, please contact Checkr at <a href='{dispute_url}'>Checkr Support</a> and email us at {support_email} within {business_days} business days so we can pause any final decision while Checkr investigates.</p>
    <p>Review your rights under the Fair Credit Reporting Act (FTC): <a href='{summary_url}'>Summary of Your Rights Under the Fair Credit Reporting Act (FTC)</a>.</p>
    <p>If we do not hear from you within {business_days} business days, final adverse action may be taken.</p>
    """.strip()

    text = (
        f"We are contacting you about your recent background report for {BRAND_NAME}. "
        "Based on information in the report, adverse action may be taken. This message is a pre-adverse action notice.\n"
        f"Review your complete background report at {portal_url}.\n"
        f"If you believe any information is inaccurate, contact Checkr at {dispute_url} and email {support_email} within "
        f"{business_days} business days so we can pause any final decision while Checkr investigates.\n"
        f"Review your rights under the Fair Credit Reporting Act (FTC): Summary of Your Rights Under the Fair Credit Reporting Act (FTC) — {summary_url}.\n"
        f"If we do not hear from you within {business_days} business days, final adverse action may be taken."
    )

    return AdverseEmailTemplate(subject=subject, html=html, text=text)


def build_final_adverse_email() -> AdverseEmailTemplate:
    """Return the subject and bodies for the final adverse action notice."""

    portal_url = settings.checkr_applicant_portal_url
    dispute_url = settings.checkr_dispute_contact_url
    summary_url = settings.ftc_summary_of_rights_url
    support_email = settings.bgc_support_email

    subject = f"{BRAND_NAME}: Final adverse action decision"

    html = f"""
    <p>We completed our review of your background report for {BRAND_NAME} and have taken adverse action.</p>
    <p>You have the right to dispute the accuracy of your report and request a reinvestigation. Contact Checkr at <a href='{dispute_url}'>Checkr Support</a> or visit <a href='{portal_url}'>{portal_url}</a> to obtain a free copy of your report.</p>
    <p>Your rights under the Fair Credit Reporting Act (FTC) are described here: <a href='{summary_url}'>Summary of Your Rights Under the Fair Credit Reporting Act (FTC)</a>.</p>
    <p>If you plan to dispute the report, please reach out to Checkr and cc {support_email} so we can monitor the review.</p>
    """.strip()

    text = (
        f"We completed our review of your background report for {BRAND_NAME} and have taken adverse action.\n"
        f"You have the right to dispute the accuracy of your report and request a reinvestigation. Contact Checkr at {dispute_url} "
        f"or visit {portal_url} to obtain a free copy of your report.\n"
        f"Your rights under the Fair Credit Reporting Act (FTC) are described here: Summary of Your Rights Under the Fair Credit Reporting Act (FTC) — {summary_url}.\n"
        f"If you plan to dispute the report, reach out to Checkr and cc {support_email} so we can monitor the review."
    )

    return AdverseEmailTemplate(subject=subject, html=html, text=text)
