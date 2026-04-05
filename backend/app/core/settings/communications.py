from __future__ import annotations

from typing import Literal

from pydantic import Field, SecretStr

from ..constants import BRAND_NAME
from .shared import DEFAULT_SENDER_PROFILES_FILE


class CommunicationsSettingsMixin:
    email_provider: Literal["console", "resend"] = Field(
        default="console",
        alias="EMAIL_PROVIDER",
        description="Email provider name",
    )
    resend_api_key: SecretStr | None = Field(
        default=None,
        alias="RESEND_API_KEY",
        description="API key for Resend provider (optional)",
    )
    from_email: str = "iNSTAiNSTRU <hello@instainstru.com>"
    email_from_address: str | None = Field(
        default=None,
        description="Optional email address for transactional sends (overrides from_email when provided)",
    )
    email_from_name: str = Field(
        default=BRAND_NAME,
        description="Display name used for transactional email sends",
    )
    email_reply_to: str | None = Field(
        default=None,
        description="Optional Reply-To address applied when sender profiles do not override it",
    )
    email_sender_profiles_file: str | None = Field(
        default=str(DEFAULT_SENDER_PROFILES_FILE),
        description="Filesystem path containing default sender profiles JSON",
    )
    email_sender_profiles_json: str | None = Field(
        default=None,
        description="JSON map of named sender profiles for transactional email",
    )
    admin_email: str = Field(default="admin@instainstru.com", alias="ADMIN_EMAIL")
    admin_name: str = Field(default="Instainstru Admin", alias="ADMIN_NAME")
    admin_password: SecretStr | None = Field(default=None, alias="ADMIN_PASSWORD")
    vapid_public_key: str = Field(
        default="",
        alias="VAPID_PUBLIC_KEY",
        description="Base64-encoded VAPID public key",
    )
    vapid_private_key: SecretStr = Field(
        default=SecretStr(""),
        alias="VAPID_PRIVATE_KEY",
        description="Base64-encoded VAPID private key (keep secret)",
    )
    vapid_claims_email: str = Field(
        default="mailto:support@instainstru.com",
        alias="VAPID_CLAIMS_EMAIL",
        description="Contact email for VAPID claims",
    )
    twilio_account_sid: str | None = Field(
        default=None,
        alias="TWILIO_ACCOUNT_SID",
        description="Twilio account SID",
    )
    twilio_auth_token: SecretStr | None = Field(
        default=None,
        alias="TWILIO_AUTH_TOKEN",
        description="Twilio auth token (keep secret)",
    )
    twilio_phone_number: str | None = Field(
        default=None,
        alias="TWILIO_PHONE_NUMBER",
        description="Twilio sending phone number in E.164 format",
    )
    twilio_messaging_service_sid: str | None = Field(
        default=None,
        alias="TWILIO_MESSAGING_SERVICE_SID",
        description="Twilio Messaging Service SID (optional)",
    )
    sms_enabled: bool = Field(
        default=False,
        alias="SMS_ENABLED",
        description="Enable SMS sending",
    )
    sms_daily_limit_per_user: int = Field(
        default=10,
        alias="SMS_DAILY_LIMIT_PER_USER",
        description="Daily SMS limit per user",
        ge=1,
    )
    email_enabled: bool = Field(default=True, description="Flag to enable/disable email sending")
    message_edit_window_minutes: int = Field(
        default=5, description="How many minutes a user can edit their message"
    )
    sse_heartbeat_interval: int = Field(default=30, description="SSE heartbeat interval in seconds")
