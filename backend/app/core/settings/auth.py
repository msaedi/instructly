from __future__ import annotations

import os
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator

from .shared import _default_secret_key, _default_session_cookie_name, secret_or_plain


class AuthSettingsMixin:
    secret_key: SecretStr = Field(
        default_factory=_default_secret_key,
        description="Secret key for JWT tokens",
    )
    algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(
        default=720,
        validation_alias=AliasChoices(
            "ACCESS_TOKEN_EXPIRE_MINUTES",
            "ACCESS_TOKEN_LIFETIME_MINUTES",
            "access_token_expire_minutes",
        ),
        description="Access token lifetime in minutes",
    )
    refresh_token_lifetime_days: int = Field(
        default=7,
        alias="REFRESH_TOKEN_LIFETIME_DAYS",
        description="Refresh token lifetime in days",
    )
    totp_encryption_key: SecretStr = Field(
        default=SecretStr(""),
        description="Fernet key for encrypting TOTP secrets (optional in dev)",
    )
    two_factor_trust_days: int = Field(default=30, description="Days to trust a browser for 2FA")
    temp_token_secret: SecretStr | None = Field(
        default=None,
        alias="TEMP_TOKEN_SECRET",
        description="Optional override secret for 2FA temp tokens (defaults to SECRET_KEY)",
    )
    email_verification_token_secret: SecretStr | None = Field(
        default=None,
        alias="EMAIL_VERIFICATION_TOKEN_SECRET",
        description="Optional override secret for email verification tokens (defaults to SECRET_KEY)",
    )
    mcp_token_secret: SecretStr = Field(
        default=SecretStr(""),
        alias="MCP_TOKEN_SECRET",
        description="Secret key for MCP confirm tokens (falls back to SECRET_KEY when unset)",
    )
    mcp_service_token: SecretStr | None = Field(
        default=None,
        alias="MCP_SERVICE_TOKEN",
        description="Service token for MCP server authentication",
    )
    mcp_service_account_email: str = Field(
        default="admin@instainstru.com",
        alias="MCP_SERVICE_ACCOUNT_EMAIL",
        description="Service account email used for MCP audit logging",
    )
    workos_jwks_url: str = Field(
        default="",
        alias="WORKOS_JWKS_URL",
        description="WorkOS JWKS URL for M2M token verification",
    )
    workos_m2m_audience: str = Field(
        default="",
        alias="WORKOS_M2M_AUDIENCE",
        description="Audience for WorkOS M2M tokens",
    )
    workos_issuer: str = Field(
        default="",
        alias="WORKOS_ISSUER",
        description="Issuer for WorkOS M2M tokens",
    )
    temp_token_iss: str = Field(
        default="instainstru-auth",
        alias="TEMP_TOKEN_ISS",
        description="Issuer claim for temporary 2FA tokens",
    )
    temp_token_aud: str = Field(
        default="instainstru-2fa",
        alias="TEMP_TOKEN_AUD",
        description="Audience claim for temporary 2FA tokens",
    )
    email_verification_token_iss: str = Field(
        default="instainstru-auth-email",
        alias="EMAIL_VERIFICATION_TOKEN_ISS",
        description="Issuer claim for email verification tokens",
    )
    email_verification_token_aud: str = Field(
        default="instainstru-email-verification",
        alias="EMAIL_VERIFICATION_TOKEN_AUD",
        description="Audience claim for email verification tokens",
    )
    session_cookie_name: str = Field(
        default_factory=_default_session_cookie_name,
        alias="SESSION_COOKIE_NAME",
        description="Session cookie name",
    )
    session_cookie_secure: bool = Field(
        default=False,
        alias="SESSION_COOKIE_SECURE",
        description="Whether session cookies must be marked Secure",
    )
    session_cookie_samesite: Literal["lax", "strict", "none"] = Field(
        default="lax",
        alias="SESSION_COOKIE_SAMESITE",
        description="SameSite attribute applied to session cookies",
    )
    session_cookie_domain: str | None = Field(
        default=None,
        description="Domain attribute for session cookies (set to .instainstru.com for hosted envs)",
    )
    totp_valid_window: int = Field(
        default=0,
        alias="TOTP_VALID_WINDOW",
        description="TOTP valid window tolerance",
    )

    @field_validator("secret_key", mode="before")
    @classmethod
    def _validate_secret_key(cls, value: SecretStr | str | None) -> SecretStr | str | None:
        if secret_or_plain(value).strip():
            return value
        if os.getenv("CI"):
            return _default_secret_key()
        raise ValueError("SECRET_KEY must be set")

    @field_validator("session_cookie_secure", mode="before")
    @classmethod
    def _coerce_cookie_secure(cls, value: object) -> bool | object:
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return value

    @field_validator("session_cookie_samesite", mode="before")
    @classmethod
    def _normalize_samesite(cls, value: object) -> str:
        if value is None:
            return "lax"
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"lax", "strict", "none"}:
                return normalized
        raise ValueError("SESSION_COOKIE_SAMESITE must be one of: lax, strict, none")
