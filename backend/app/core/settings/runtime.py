from __future__ import annotations

from pydantic import Field, SecretStr

from .shared import _default_environment


class RuntimeSettingsMixin:
    frontend_url: str = "https://beta.instainstru.com"
    invite_claim_base_url: str = Field(
        default="https://instainstru.com",
        description="Public-facing root used for invite claim links",
    )
    identity_return_path: str = "/instructor/onboarding/verification?identity_return=true"
    local_beta_frontend_origin: str = Field(
        default="http://beta-local.instainstru.com:3000",
        description="Local-only override for beta invite links",
    )
    frontend_referral_landing_url: str = Field(
        default="https://beta.instainstru.com/referral",
        description="Landing page for public referral links",
    )
    environment: str = Field(default_factory=_default_environment)
    is_testing: bool = False
    staff_preview_token: SecretStr = Field(default=SecretStr(""), alias="staff_preview_token")
    allow_preview_header: bool = Field(default=False, alias="allow_preview_header")
    preview_frontend_domain: str = Field(
        default="preview.instainstru.com", alias="preview_frontend_domain"
    )
    preview_api_domain: str = Field(
        default="preview-api.instainstru.com", alias="preview_api_domain"
    )
    prod_api_domain: str = Field(default="api.instainstru.com", alias="prod_api_domain")
    prod_frontend_origins_csv: str = Field(
        default="https://beta.instainstru.com,https://app.instainstru.com",
        alias="prod_frontend_origins",
    )
