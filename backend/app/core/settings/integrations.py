from __future__ import annotations

import os
from typing import cast

from pydantic import AliasChoices, Field, SecretStr, model_validator


class IntegrationsSettingsMixin:
    checkr_env: str = Field(
        default="sandbox",
        description="Target Checkr environment (sandbox|production)",
    )
    checkr_fake: bool = Field(
        default=False,
        alias="CHECKR_FAKE",
        description="When true, use the FakeCheckr client. Defaults to true outside production.",
    )
    allow_sandbox_checkr_in_prod: bool = Field(
        default=False,
        alias="ALLOW_SANDBOX_CHECKR_IN_PROD",
        description="Allow Checkr sandbox while in prod/beta without enabling FakeCheckr.",
    )
    checkr_api_key: SecretStr = Field(
        default=SecretStr(""),
        description="Checkr API key for background check operations",
    )
    checkr_package: str = Field(
        default="basic_plus",
        validation_alias=AliasChoices("CHECKR_DEFAULT_PACKAGE", "CHECKR_PACKAGE"),
        description="Default Checkr package to request for instructor background checks",
    )
    checkr_api_base: str = Field(
        default="https://api.checkr.com/v1",
        description="Base URL for Checkr API",
    )
    checkr_webhook_secret: SecretStr = Field(
        default=SecretStr(""),
        description="Shared secret for verifying Checkr webhook signatures",
    )
    checkr_webhook_user: SecretStr | None = Field(
        default=None,
        alias="CHECKR_WEBHOOK_USER",
        description="Optional basic-auth username expected on Checkr webhook requests",
    )
    checkr_webhook_pass: SecretStr | None = Field(
        default=None,
        alias="CHECKR_WEBHOOK_PASS",
        description="Optional basic-auth password expected on Checkr webhook requests",
    )
    checkr_hosted_workflow: str | None = Field(
        default=None,
        description="Optional workflow parameter for Checkr invitations (e.g., checkr_hosted)",
    )
    checkr_applicant_portal_url: str = Field(
        default="https://applicant.checkr.com/",
        description="URL for applicants to access their Checkr reports",
    )
    checkr_dispute_contact_url: str = Field(
        default="https://help.checkr.com/hc/en-us/articles/217419328-Contact-Checkr",
        description="URL with instructions to contact Checkr regarding disputes",
    )
    ftc_summary_of_rights_url: str = Field(
        default="https://www.consumerfinance.gov/learnmore/",
        description="Link to the FTC Summary of Your Rights Under the FCRA",
    )
    bgc_support_email: str = Field(
        default="support@instainstru.com",
        description="Contact email for iNSTAiNSTRU background check questions",
    )
    bgc_suppress_adverse_emails: bool = Field(
        default=True,
        description="When true, suppress adverse-action email delivery (non-prod default)",
    )
    bgc_suppress_expiry_emails: bool = Field(
        default=True,
        description="When true, suppress background-check expiry reminder emails",
    )
    bgc_expiry_enabled: bool = Field(
        default=False,
        description="Enable automated background-check expiry sweeps and demotions",
    )
    bgc_encryption_key: SecretStr | None = Field(
        default=None,
        description="Base64-encoded 32-byte key for encrypting background check data",
    )
    hundredms_access_key: str | None = Field(
        default=None,
        alias="HUNDREDMS_ACCESS_KEY",
        description="100ms app access key for management token generation",
    )
    hundredms_app_secret: SecretStr | None = Field(
        default=None,
        alias="HUNDREDMS_APP_SECRET",
        description="100ms app secret for signing management and auth JWTs",
    )
    hundredms_template_id: str | None = Field(
        default=None,
        alias="HUNDREDMS_TEMPLATE_ID",
        description="Default 100ms template ID for room creation",
    )
    hundredms_webhook_secret: SecretStr | None = Field(
        default=None,
        alias="HUNDREDMS_WEBHOOK_SECRET",
        description="Shared secret for verifying 100ms webhook signatures",
    )
    hundredms_base_url: str = Field(
        default="https://api.100ms.live/v2",
        description="Base URL for 100ms REST API",
    )
    hundredms_enabled: bool = Field(
        default=False,
        alias="HUNDREDMS_ENABLED",
        description="Enable 100ms video integration",
    )
    r2_enabled: bool = Field(
        default=True,
        alias="R2_ENABLED",
        description="Toggle Cloudflare R2 integration (set to false/0 to disable)",
    )
    r2_account_id: str = Field(default="", description="Cloudflare R2 Account ID")
    r2_access_key_id: str = Field(default="", description="R2 access key ID")
    r2_secret_access_key: SecretStr = Field(
        default=SecretStr(""), description="R2 secret access key"
    )
    r2_bucket_name: str = Field(default="", description="R2 bucket name")
    r2_public_base_url: str = Field(
        default="https://assets.instainstru.com",
        description="Base URL for publicly served assets (if applicable)",
    )

    @model_validator(mode="after")
    def _default_checkr_base(self) -> "IntegrationsSettingsMixin":
        """Align Checkr base URL with the configured environment when unset."""

        fields_set = cast(set[str], getattr(self, "model_fields_set", set()))
        env_override = "CHECKR_API_BASE" in os.environ or "checkr_api_base" in fields_set
        if env_override:
            return self

        normalized_env = (self.checkr_env or "sandbox").strip().lower()
        if normalized_env == "sandbox":
            self.checkr_api_base = "https://api.checkr-staging.com/v1"
        else:
            self.checkr_api_base = "https://api.checkr.com/v1"
        return self
