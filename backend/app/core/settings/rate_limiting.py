from __future__ import annotations

from pydantic import Field, SecretStr


class RateLimitingSettingsMixin:
    rate_limit_enabled: bool = Field(
        default=True, description="Enable rate limiting (disable for testing)"
    )
    login_concurrency_limit: int = Field(
        default=10,
        alias="LOGIN_CONCURRENCY_LIMIT",
        description="Max concurrent login verifications allowed (controls Argon2 load)",
    )
    login_concurrency_timeout_seconds: float = Field(
        default=5.0,
        alias="LOGIN_CONCURRENCY_TIMEOUT",
        description="Seconds to wait for a login slot before returning 429",
    )
    login_attempts_per_minute: int = Field(
        default=5,
        alias="LOGIN_ATTEMPTS_PER_MINUTE",
        description="Per-account login attempts allowed per minute",
    )
    login_attempts_per_hour: int = Field(
        default=20,
        alias="LOGIN_ATTEMPTS_PER_HOUR",
        description="Per-account login attempts allowed per hour",
    )
    captcha_failure_threshold: int = Field(
        default=3,
        alias="CAPTCHA_FAILURE_THRESHOLD",
        description="Number of failed logins before CAPTCHA is required",
    )
    turnstile_secret_key: SecretStr = Field(
        default=SecretStr(""),
        alias="TURNSTILE_SECRET_KEY",
        description="Cloudflare Turnstile secret key (empty disables CAPTCHA)",
    )
    turnstile_site_key: str = Field(
        default="",
        alias="TURNSTILE_SITE_KEY",
        description="Cloudflare Turnstile site key (for frontend)",
    )
    rate_limit_general_per_minute: int = Field(
        default=150,
        description="General API rate limit per minute per IP. NL search now returns all embedded data in one request, eliminating N+1 queries.",
    )
    rate_limit_auth_per_minute: int = Field(
        default=20,
        description="Authentication attempts per minute per IP (generous - DDoS protection only; email-based limiting handles brute force)",
    )
    rate_limit_password_reset_per_hour: int = Field(
        default=5, description="Password reset requests per hour per email"
    )
    rate_limit_password_reset_ip_per_hour: int = Field(
        default=10, description="Password reset requests per hour per IP"
    )
    rate_limit_register_per_hour: int = Field(
        default=10, description="Registration attempts per hour per IP"
    )
    rate_limit_booking_per_minute: int = Field(
        default=20, description="Booking requests per minute per user"
    )
    rate_limit_expensive_per_minute: int = Field(
        default=10, description="Expensive operations per minute per user"
    )
    rate_limit_bypass_token: SecretStr = Field(
        default=SecretStr(""), description="Token to bypass rate limiting (for load testing)"
    )
