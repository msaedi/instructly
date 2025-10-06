"""
Template registry for strongly-typed access to Jinja templates.

Use with TemplateService to avoid stringly-typed paths.
"""

from enum import Enum


class TemplateRegistry(str, Enum):
    # Auth
    AUTH_PASSWORD_RESET = "email/auth/password_reset.html"
    AUTH_PASSWORD_RESET_CONFIRMATION = "email/auth/password_reset_confirmation.html"

    # Referrals
    REFERRALS_INVITE = "email/referrals/invite.html"
    REFERRALS_INVITE_STANDALONE = "email/referrals/invite_standalone.html"

    # Beta invites
    BETA_INVITE = "email/beta/invite.html"

    # Background checks
    BGC_PRE_ADVERSE = "email/bgc/pre_adverse.jinja"
    BGC_FINAL_ADVERSE = "email/bgc/final_adverse.jinja"
    BGC_EXPIRY_RECHECK = "email/bgc/expiry_recheck.jinja"
