"""
Centralized email subject builders.

Keep subjects in code (not templates) for versioning, logging,
and future i18n. Bodies remain in Jinja templates.
"""

from app.core.constants import BRAND_NAME


class EmailSubject:
    """Utility class with static builders for email subjects."""

    @staticmethod
    def referral_invite(inviter_name: str) -> str:
        safe_name = inviter_name.strip() or "A friend"
        return f"{safe_name} invited you to try {BRAND_NAME}"

    @staticmethod
    def password_reset() -> str:
        return f"Reset Your {BRAND_NAME} Password"

    @staticmethod
    def password_reset_confirmation() -> str:
        return f"Your {BRAND_NAME} Password Has Been Reset"

    @staticmethod
    def welcome() -> str:
        return f"Welcome to {BRAND_NAME}!"

    @staticmethod
    def beta_invite() -> str:
        return f"You're invited to {BRAND_NAME} (Founding Instructor)"
