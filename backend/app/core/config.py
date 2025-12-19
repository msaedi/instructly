# backend/app/core/config.py
from email.utils import parseaddr
import json
import logging
import os
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Literal,
    Mapping,
    NotRequired,
    Optional,
    Set,
    TypedDict,
    cast,
)

if TYPE_CHECKING:
    load_dotenv: Callable[..., bool]
try:
    from dotenv import load_dotenv as _real_load_dotenv

    load_dotenv = cast(Callable[..., bool], _real_load_dotenv)
except Exception:  # pragma: no cover - optional on CI

    def load_dotenv(*_args: Any, **_kwargs: Any) -> bool:
        return False


from pydantic import (
    AliasChoices,
    Field,
    PrivateAttr,
    SecretStr,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from .constants import BRAND_NAME


def is_running_tests() -> bool:
    """
    Detect if code is running under pytest.

    PYTEST_CURRENT_TEST is set automatically by pytest during test runs, and is
    not expected to be present in production environments.
    """
    return os.getenv("PYTEST_CURRENT_TEST") is not None


_BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SENDER_PROFILES_FILE = _BACKEND_ROOT / "config" / "email_senders.json"

logger = logging.getLogger(__name__)

# Load .env file only if not in CI
if not os.getenv("CI"):
    env_path = Path(__file__).parent.parent.parent / ".env"  # Goes up to backend/.env
    logger.info(f"[CONFIG] Looking for .env at: {env_path}")
    logger.info(f"[CONFIG] .env exists: {env_path.exists()}")
    logger.info(f"[CONFIG] Absolute path: {env_path.absolute()}")
    load_dotenv(env_path)


NON_PROD_SITE_MODES: Set[str] = {
    "local",
    "dev",
    "development",
    "int",
    "stg",
    "stage",
    "staging",
    "preview",
}
PROD_SITE_MODES: Set[str] = {"prod", "production", "beta", "live"}


def _classify_site_mode(raw_site_mode: str | None) -> tuple[str, bool, bool]:
    """Return normalized site mode with production/non-prod classification."""

    normalized = (raw_site_mode or "").strip().lower()
    is_prod = normalized in PROD_SITE_MODES
    is_non_prod = normalized in NON_PROD_SITE_MODES
    return normalized, is_prod, is_non_prod


def _default_session_cookie_name() -> str:
    """Return default session cookie name."""

    return "__Host-sid"


def resolve_referrals_step(
    *,
    raw_value: str | None = None,
    site_mode: str | None = None,
    env: Mapping[str, str] | None = None,
) -> int:
    """
    Resolve REFERRALS_UNSAFE_STEP with safe defaults for non-production environments.

    When the env var is unset, return 4 for local/dev/stg-like modes so referral issuance
    remains enabled by default. Production defaults remain unchanged.
    """

    env_map = env or os.environ
    value = raw_value if raw_value is not None else env_map.get("REFERRALS_UNSAFE_STEP")
    cleaned = (value or "").strip()
    if cleaned:
        try:
            return max(0, int(cleaned))
        except ValueError:
            logger.warning("Invalid REFERRALS_UNSAFE_STEP=%s; defaulting to 0", cleaned)
            return 0

    normalized_mode, is_prod, is_non_prod = _classify_site_mode(
        site_mode or env_map.get("SITE_MODE")
    )
    if is_prod:
        return 0
    if is_non_prod or not normalized_mode:
        return 4
    # Treat everything outside explicit prod bucket as non-prod for safety.
    return 4


class SenderProfile(TypedDict):
    from_name: str
    from_: str
    reply_to: NotRequired[str]


class SenderProfileResolved(TypedDict):
    from_name: str
    from_address: str
    reply_to: str | None


if os.getenv("CI"):
    _DEFAULT_SECRET_KEY: SecretStr | object = SecretStr("ci-test-secret-key-not-for-production")
else:
    _DEFAULT_SECRET_KEY = ...


class Settings(BaseSettings):
    # Use a default secret key for CI/testing environments
    secret_key: SecretStr = Field(
        default=_DEFAULT_SECRET_KEY,
        description="Secret key for JWT tokens",
    )  # type: ignore[assignment]  # defaults to ellipsis outside CI; SecretStr default provided for CI runs
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 720  # 12 hours

    # 2FA / TOTP
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
        description="Optional Domain attribute for session cookies (omit for __Host- cookies)",
    )
    email_provider: Literal["console", "resend"] = Field(
        default="console",
        alias="EMAIL_PROVIDER",
        description="Email provider name",
    )
    resend_api_key: str | None = Field(
        default=None,
        alias="RESEND_API_KEY",
        description="API key for Resend provider (optional)",
    )
    totp_valid_window: int = Field(
        default=0,
        alias="TOTP_VALID_WINDOW",
        description="TOTP valid window tolerance",
    )

    # Raw database URLs - DO NOT USE DIRECTLY! Use properties instead
    # Explicit env names (no backward compatibility):
    #  - prod_database_url
    #  - preview_database_url
    #  - stg_database_url
    #  - test_database_url
    prod_database_url_raw: Optional[str] = Field(
        default=None, alias="prod_database_url"
    )  # From env PROD_DATABASE_URL
    prod_service_database_url_raw: Optional[str] = Field(
        default=None, alias="prod_service_database_url"
    )
    preview_database_url_raw: str = Field(
        default="", alias="preview_database_url"
    )  # From env PREVIEW_DATABASE_URL
    preview_service_database_url_raw: Optional[str] = Field(
        default=None, alias="preview_service_database_url"
    )
    int_database_url_raw: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/instainstru_test"
        if os.getenv("CI")
        else "",
        alias="test_database_url",
    )  # From env TEST_DATABASE_URL
    stg_database_url_raw: str = Field("", alias="stg_database_url")  # From env STG_DATABASE_URL

    # Legacy flags for backward compatibility
    is_testing: bool = False  # Set to True when running tests

    # Email settings
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
    admin_password: str | None = Field(default=None, alias="ADMIN_PASSWORD")

    # Frontend URL - will use production URL if not set
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

    # Environment (derived from SITE_MODE)
    environment: str = (
        "production" if _classify_site_mode(os.getenv("SITE_MODE", "local"))[1] else "development"
    )

    # Checkr configuration
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
    bgc_encryption_key: str | None = Field(
        default=None,
        description="Base64-encoded 32-byte key for encrypting background check data",
    )
    scheduler_enabled: bool = Field(
        default=True,
        description="Enable background schedulers (disabled automatically during tests)",
    )
    jobs_backoff_base: int = Field(
        default=30,
        description="Base backoff in seconds for background job retries",
        ge=1,
    )
    jobs_backoff_cap: int = Field(
        default=1800,
        description="Maximum backoff in seconds for background job retries",
        ge=1,
    )
    jobs_poll_interval: int = Field(
        default=2,
        description="Background job worker poll interval in seconds",
        ge=1,
    )
    jobs_batch: int = Field(
        default=25,
        description="Maximum number of jobs processed per polling interval",
        ge=1,
    )
    jobs_max_attempts: int = Field(
        default=5,
        description="Maximum retry attempts before moving a job to the dead-letter queue",
        ge=1,
    )
    connect_return_path: str = Field(
        default="/instructor/onboarding/connect?connect_return=1",
        description="Frontend callback path after Stripe Connect onboarding",
    )
    metrics_ip_allowlist: list[str] = Field(
        default_factory=list,
        description="Comma-separated IPs/CIDRs allowed for /internal/metrics (when non-empty)",
    )
    metrics_max_bytes: int = Field(
        default=8_000_000,
        description="Cap response size for metrics",
        ge=1,
    )
    metrics_rate_limit_per_min: int = Field(
        default=6,
        description="Per-IP requests/minute for /internal/metrics",
        ge=1,
    )

    metrics_basic_auth_user: SecretStr | None = Field(
        default=None,
        description="Optional username for protecting /metrics",
    )
    metrics_basic_auth_pass: SecretStr | None = Field(
        default=None,
        description="Optional password for protecting /metrics",
    )

    _sender_profiles: dict[str, SenderProfile] = PrivateAttr(default_factory=dict)
    _sender_profiles_warning_logged: bool = PrivateAttr(default=False)

    @property
    def site_mode(self) -> Literal["local", "preview", "prod"]:
        """Return canonical site mode derived from SITE_MODE."""
        normalized, is_prod, _ = _classify_site_mode(os.getenv("SITE_MODE", ""))
        if normalized == "preview":
            return "preview"
        if is_prod:
            return "prod"
        return "local"

    @property
    def referrals_step(self) -> int:
        """Return resolved referrals issuance step honoring environment defaults."""
        return resolve_referrals_step(site_mode=self.site_mode)

    @property
    def metrics_basic_auth_enabled(self) -> bool:
        mode = (self.site_mode or "").lower()
        raw_mode = (os.getenv("SITE_MODE", "") or "").strip().lower()
        if mode not in {"preview", "prod"} and raw_mode != "beta":
            return False
        return self.metrics_basic_auth_user is not None and self.metrics_basic_auth_pass is not None

    def env_bool(self, name: str, default: bool = False) -> bool:
        raw = os.getenv(name)
        if raw is None:
            return default
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    @field_validator("metrics_ip_allowlist", mode="before")
    @classmethod
    def _parse_metrics_ip_allowlist(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            items = [token.strip() for token in value.split(",") if token.strip()]
            return items
        if isinstance(value, (list, tuple, set)):
            items = [str(token).strip() for token in value if str(token).strip()]
            return items
        raise ValueError("metrics_ip_allowlist must be a comma-separated string or list")

    # Cache settings
    redis_url: str = "redis://localhost:6379"
    cache_ttl: int = 3600  # 1 hour in seconds

    # Search Analytics Configuration
    guest_session_expiry_days: int = 30  # How long to keep guest sessions
    soft_delete_retention_days: int = 90  # How long to keep soft-deleted searches
    guest_session_purge_days: int = 90  # When to permanently delete guest sessions
    search_history_max_per_user: int = (
        1000  # Maximum searches to keep per user (set to 0 to disable limit)
    )
    search_analytics_enabled: bool = True  # Enable/disable analytics tracking

    # OpenAI Location Resolution (Tier 5)
    openai_location_model: str = Field(
        default="gpt-4o-mini",
        alias="OPENAI_LOCATION_MODEL",
        description="Model used for Tier 5 location resolution",
    )
    openai_location_timeout_ms: int = Field(
        default=3000,
        alias="OPENAI_LOCATION_TIMEOUT_MS",
        ge=500,
        description="Timeout (ms) for Tier 5 location resolution",
    )

    # Privacy and Data Retention Configuration (GDPR compliance)
    search_event_retention_days: int = 365  # Keep detailed search events for 1 year
    booking_pii_retention_days: int = 2555  # Keep booking PII for 7 years (business requirement)
    alert_retention_days: int = 365  # Keep alert history for 1 year
    privacy_data_export_enabled: bool = (
        True  # Enable user data export (GDPR right to data portability)
    )
    privacy_data_deletion_enabled: bool = (
        True  # Enable user data deletion (GDPR right to be forgotten)
    )
    availability_retention_enabled: bool = Field(
        default=False,
        alias="AVAILABILITY_RETENTION_ENABLED",
        description="Enable scheduled purge of stale availability_days rows",
    )
    availability_retention_days: int = Field(
        default=180,
        alias="AVAILABILITY_RETENTION_DAYS",
        ge=0,
        description="TTL in days before bitmap availability entries become purge candidates",
    )
    availability_retention_keep_recent_days: int = Field(
        default=30,
        alias="AVAILABILITY_RETENTION_KEEP_RECENT_DAYS",
        ge=0,
        description="Minimum recent history (days) to always keep even if TTL exceeded",
    )
    availability_retention_dry_run: bool = Field(
        default=False,
        alias="AVAILABILITY_RETENTION_DRY_RUN",
        description="When true, retention logs counts without deleting availability_days rows",
    )

    # Production database protection
    production_database_indicators: list[str] = [
        "supabase.com",
        "supabase.co",
        "amazonaws.com",
        "cloud.google.com",
        "database.azure.com",
        "elephantsql.com",
        "bit.io",
        "neon.tech",
        "railway.app",
        "render.com",
        "aiven.io",
    ]

    # Use ConfigDict instead of Config class (Pydantic V2 style)
    model_config = SettingsConfigDict(
        env_file=".env" if not os.getenv("CI") else None,
        case_sensitive=False,  # Changed to False - allows SECRET_KEY to match secret_key
        extra="ignore",
    )

    @model_validator(mode="after")
    def _derive_cookie_policy(self) -> "Settings":
        """Normalize session cookie attributes per site mode."""

        raw_mode = (os.getenv("SITE_MODE", "") or "").strip().lower()
        normalized, is_prod, is_non_prod = _classify_site_mode(raw_mode or self.site_mode)
        hosted = normalized == "preview" or is_prod or normalized in {"stg", "stage", "staging"}

        if hosted:
            self.session_cookie_secure = True
            self.session_cookie_samesite = "lax"
            # __Host- cookies require Domain omission
            self.session_cookie_domain = None
        elif not is_prod and not is_non_prod:
            # Unknown modes default to secure cookies unless explicitly disabled
            self.session_cookie_secure = bool(self.session_cookie_secure)
        # Keep caller-provided overrides for non-hosted environments (e.g., local HTTP)

        if not bool(self.session_cookie_secure) and str(self.session_cookie_name or "").startswith(
            "__Host-"
        ):
            logger.warning(
                "SESSION_COOKIE_NAME %s uses __Host- prefix but SESSION_COOKIE_SECURE is false. "
                "For local HTTP, set SESSION_COOKIE_NAME=sid_local (or similar) or enable HTTPS.",
                self.session_cookie_name,
            )
        return self

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

    # Public API Configuration
    public_availability_days: int = Field(
        default=30,
        description="Maximum number of days to show in public availability",
        ge=1,  # Greater than or equal to 1
        le=90,  # Less than or equal to 90
    )

    public_availability_detail_level: Literal["full", "summary", "minimal"] = Field(
        default="full", description="Level of detail to show in public availability endpoints"
    )

    public_availability_show_instructor_name: bool = Field(
        default=True, description="Whether to show instructor names in public endpoints"
    )

    public_availability_cache_ttl: int = Field(
        default=300,
        description="Cache TTL in seconds for public availability data",  # 5 minutes
    )

    past_edit_window_days: int = Field(
        default=0,
        alias="PAST_EDIT_WINDOW_DAYS",
        ge=0,
        description="Maximum number of days in the past that bitmap edits will write; 0 = no limit",
    )
    clamp_copy_to_future: bool = Field(
        default=False,
        alias="CLAMP_COPY_TO_FUTURE",
        description="Skip bitmap apply/copy writes for target dates before today",
    )
    feature_disable_slot_writes: bool = Field(
        default=True,
        alias="FEATURE_DISABLE_SLOT_WRITES",
        description="When true, legacy availability_slots writes are disabled",
    )
    seed_disable_slots: bool = Field(
        default=True,
        alias="SEED_DISABLE_SLOTS",
        description="When true, seed scripts skip inserting availability_slots rows",
    )
    include_empty_days_in_tests: bool = Field(
        default=False,
        alias="INCLUDE_EMPTY_DAYS_IN_TESTS",
        description="When true, weekly availability responses include empty days (test-only helper)",
    )
    instant_deliver_in_tests: bool = Field(
        default=True,
        alias="INSTANT_DELIVER_IN_TESTS",
        description="When true, availability outbox events are marked sent immediately during tests",
    )
    suppress_past_availability_events: bool = Field(
        default=False,
        alias="SUPPRESS_PAST_AVAILABILITY_EVENTS",
        description="When true, availability events with only past dates are suppressed",
    )

    # Rate Limiting Configuration
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
    turnstile_secret_key: str = Field(
        default="",
        alias="TURNSTILE_SECRET_KEY",
        description="Cloudflare Turnstile secret key (empty disables CAPTCHA)",
    )
    turnstile_site_key: str = Field(
        default="",
        alias="TURNSTILE_SITE_KEY",
        description="Cloudflare Turnstile site key (for frontend)",
    )

    rate_limit_general_per_minute: int = Field(
        default=100,
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

    # Rate limit bypass for testing
    rate_limit_bypass_token: str = Field(
        default="", description="Token to bypass rate limiting (for load testing)"
    )

    # Template Caching Configuration
    template_cache_enabled: bool = Field(
        default=True,
        description="Enable template service caching (disable for development if needed)",
    )

    # Messaging configuration
    message_edit_window_minutes: int = Field(
        default=5, description="How many minutes a user can edit their message"
    )
    sse_heartbeat_interval: int = Field(default=30, description="SSE heartbeat interval in seconds")

    # Geocoding/Maps providers
    geocoding_provider: str = Field(
        default="google", description="Geocoding provider: google|mapbox|mock"
    )
    google_maps_api_key: str = Field(
        default="", description="Google Maps API key for geocoding/places"
    )
    mapbox_access_token: str = Field(
        default="", description="Mapbox access token for geocoding/search"
    )

    # Referral program configuration (Instainstru Park Slope beta)
    referrals_enabled: bool = Field(default=True, description="Enable referral flows")
    referrals_student_amount_cents: int = Field(
        default=2000, description="Reward amount for student-side credits"
    )
    referrals_instructor_amount_cents: int = Field(
        default=5000, description="Reward amount for instructor-side credits"
    )
    referrals_min_basket_cents: int = Field(
        default=7500, description="Minimum order amount to apply referral credit"
    )
    referrals_hold_days: int = Field(default=7, description="Days to hold rewards before unlock")
    referrals_expiry_months: int = Field(
        default=6, description="Months before unlocked rewards expire"
    )
    referrals_student_global_cap: int = Field(
        default=200, description="Maximum active student rewards per referrer"
    )

    # Stripe Configuration
    stripe_publishable_key: str = Field(
        default="", description="Stripe publishable key for frontend"
    )
    stripe_secret_key: SecretStr = Field(
        default=SecretStr(""),
        description="Stripe secret key for backend API calls",
    )

    # Webhook secrets - backward compatible for both local and deployed environments
    stripe_webhook_secret: SecretStr = Field(
        default=SecretStr(""),
        description="Stripe webhook secret for local dev (Stripe CLI)",
    )
    stripe_webhook_secret_platform: SecretStr = Field(
        default=SecretStr(""),
        description="Platform events webhook secret (deployed)",
    )
    stripe_webhook_secret_connect: SecretStr = Field(
        default=SecretStr(""),
        description="Connect events webhook secret (deployed)",
    )

    stripe_platform_fee_percentage: float = Field(
        default=15, description="Platform fee percentage (15 = 15%)"
    )
    stripe_currency: str = Field(default="usd", description="Default currency for payments")

    # Preview staff access (for API-side preview bypass)
    staff_preview_token: str = Field(default="", alias="staff_preview_token")
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

    # Cloudflare R2 (S3-compatible) configuration for asset uploads
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

    # Prometheus HTTP API (optional)
    prometheus_http_url: str = Field(
        default="", description="Prometheus base URL, e.g., http://localhost:9090"
    )
    prometheus_bearer_token: str = Field(
        default="", description="Optional bearer token for Prometheus API"
    )
    email_enabled: bool = Field(default=True, description="Flag to enable/disable email sending")

    @property
    def webhook_secrets(self) -> list[str]:
        """Build list of webhook secrets to try in order."""
        secrets = []

        # Add local dev secret if configured
        if self.stripe_webhook_secret:
            secret_str = (
                self.stripe_webhook_secret.get_secret_value()
                if hasattr(self.stripe_webhook_secret, "get_secret_value")
                else str(self.stripe_webhook_secret)
            )
            if secret_str:
                secrets.append(secret_str)

        # Add platform secret if configured
        if self.stripe_webhook_secret_platform:
            secret_str = (
                self.stripe_webhook_secret_platform.get_secret_value()
                if hasattr(self.stripe_webhook_secret_platform, "get_secret_value")
                else str(self.stripe_webhook_secret_platform)
            )
            if secret_str:
                secrets.append(secret_str)

        # Add connect secret if configured
        if self.stripe_webhook_secret_connect:
            secret_str = (
                self.stripe_webhook_secret_connect.get_secret_value()
                if hasattr(self.stripe_webhook_secret_connect, "get_secret_value")
                else str(self.stripe_webhook_secret_connect)
            )
            if secret_str:
                secrets.append(secret_str)

        return secrets

    @field_validator("bgc_encryption_key")
    @classmethod
    def require_bgc_key_in_prod(cls, value: str | None, info: ValidationInfo) -> str | None:
        """Ensure encryption key is configured when running in production."""

        environment = info.data.get("environment", "development")
        if environment == "production" and not value:
            raise ValueError("BGC_ENCRYPTION_KEY must be set in production environments.")
        return value

    @field_validator("int_database_url_raw")
    @classmethod
    def validate_test_database(cls, v: str, info: ValidationInfo) -> str:
        """Ensure test database is not a production database."""
        if not v:
            return v

        # Get the list of production indicators from the values
        prod_indicators = cast(list[str], info.data.get("production_database_indicators", []))

        # Check if test database URL contains any production indicators
        for indicator in prod_indicators:
            if indicator in v.lower():
                raise ValueError(
                    f"Test database URL contains production indicator '{indicator}'. "
                    f"Tests must not use production databases!"
                )

        # Ensure test database has clear test indicators
        test_indicators = ["test", "testing", "_test", "-test"]
        has_test_indicator = any(indicator in v.lower() for indicator in test_indicators)

        if not has_test_indicator:
            logger.warning(
                "Test database URL doesn't contain 'test' in its name. "
                "Consider using a clearly named test database."
            )

        return v

    def get_database_url(self) -> str:
        """Get the appropriate database URL based on context."""
        # Import here to avoid circular dependency
        from .database_config import DatabaseConfig

        # Use the new database configuration system
        try:
            db_config = DatabaseConfig()
            return db_config.get_database_url()
        except Exception:
            # Surface error immediately; do not fall back to legacy behavior
            raise

    def is_production_database(self, url: str | None = None) -> bool:
        """Check if a database URL appears to be a production database."""
        check_url = url or self.prod_database_url_raw or ""
        return any(
            indicator in check_url.lower() for indicator in self.production_database_indicators
        )

    @property
    def database_url(self) -> str:
        """SAFE database URL property resolved via DatabaseConfig and SITE_MODE."""
        # Import here to avoid circular dependency
        from .database_config import DatabaseConfig

        db_config = DatabaseConfig()
        return db_config.get_database_url()

    @property
    def test_database_url(self) -> str:
        """Backward compatibility - always returns INT database."""
        return self.int_database_url_raw

    @property
    def stg_database_url(self) -> str:
        """Staging database URL."""
        return self.stg_database_url_raw

    @model_validator(mode="after")
    def _load_sender_profiles(self) -> "Settings":
        self.refresh_sender_profiles(self.email_sender_profiles_json)
        return self

    @model_validator(mode="after")
    def _default_checkr_fake(self) -> "Settings":
        """Ensure FakeCheckr is enabled by default in non-production environments."""

        fields_set = cast(Set[str], getattr(self, "model_fields_set", set()))
        has_env_flag = "CHECKR_FAKE" in os.environ
        if "checkr_fake" not in fields_set and not has_env_flag:
            _, is_prod, is_non_prod = _classify_site_mode(os.getenv("SITE_MODE", ""))
            if is_non_prod and not is_prod:
                self.checkr_fake = True
            elif is_prod:
                self.checkr_fake = False
        return self

    @model_validator(mode="after")
    def _default_checkr_base(self) -> "Settings":
        """Align Checkr base URL with the configured environment when unset."""

        fields_set = cast(Set[str], getattr(self, "model_fields_set", set()))
        env_override = "CHECKR_API_BASE" in os.environ or "checkr_api_base" in fields_set
        if env_override:
            return self

        normalized_env = (self.checkr_env or "sandbox").strip().lower()
        if normalized_env == "sandbox":
            self.checkr_api_base = "https://api.checkr-staging.com/v1"
        else:
            self.checkr_api_base = "https://api.checkr.com/v1"
        return self

    @model_validator(mode="after")
    def _default_bitmap_guardrails(self) -> "Settings":
        """Apply environment-based defaults for bitmap past-edit guardrails."""

        fields_set = cast(Set[str], getattr(self, "model_fields_set", set()))
        env = os.environ
        normalized_mode, is_prod, is_non_prod = _classify_site_mode(env.get("SITE_MODE"))
        guardrails_enabled = normalized_mode in {
            "prod",
            "production",
            "beta",
            "live",
            "stg",
            "stage",
            "staging",
        }
        if (
            not guardrails_enabled
            and is_non_prod
            and normalized_mode not in {"local", "dev", "development"}
        ):
            # Treat non-local staging-style modes (e.g., preview) as guardrail-enabled.
            guardrails_enabled = normalized_mode not in {"int", "test"}

        if "past_edit_window_days" not in fields_set and "PAST_EDIT_WINDOW_DAYS" not in env:
            self.past_edit_window_days = 30 if guardrails_enabled else 0
        self.past_edit_window_days = max(0, self.past_edit_window_days)

        if "clamp_copy_to_future" not in fields_set and "CLAMP_COPY_TO_FUTURE" not in env:
            self.clamp_copy_to_future = guardrails_enabled

        if (
            "suppress_past_availability_events" not in fields_set
            and "SUPPRESS_PAST_AVAILABILITY_EVENTS" not in env
        ):
            self.suppress_past_availability_events = guardrails_enabled

        return self

    def refresh_sender_profiles(self, raw_json: str | None = None) -> None:
        """Re-parse sender profiles from configuration file and JSON overlay."""

        if raw_json is not None:
            self.email_sender_profiles_json = raw_json

        file_profiles = self._load_sender_profiles_from_file(self.email_sender_profiles_file)
        env_profiles = self._parse_sender_profiles(
            self.email_sender_profiles_json,
            allow_partial=True,
        )

        merged: dict[str, SenderProfile] = {}
        for key in set(file_profiles) | set(env_profiles):
            base_profile = file_profiles.get(key)
            overrides = env_profiles.get(key, {})

            from_name = overrides.get("from_name")
            if not from_name and base_profile is not None:
                from_name = base_profile.get("from_name", "")

            from_address = overrides.get("from_")
            if not from_address and base_profile is not None:
                from_address = base_profile.get("from_", "")

            reply_override = overrides.get("reply_to")
            base_reply = base_profile.get("reply_to") if base_profile else None
            reply_to = reply_override if reply_override else base_reply

            if not from_name and not from_address and not reply_to:
                continue

            profile: SenderProfile = {
                "from_name": from_name or "",
                "from_": from_address or "",
            }
            if reply_to:
                profile["reply_to"] = reply_to
            merged[key] = profile

        self._sender_profiles = merged

    def resolve_sender_profile(self, key: str | None) -> SenderProfileResolved:
        """Return a resolved sender profile for the given key with defaults applied."""

        default_profile = self._default_sender_profile()
        if key:
            profile = self._sender_profiles.get(key)
            if profile:
                from_name = profile.get("from_name", "").strip() or default_profile["from_name"]
                from_address = profile.get("from_", "").strip() or default_profile["from_address"]
                reply_to_raw = profile.get("reply_to")
                reply_to = reply_to_raw.strip() if isinstance(reply_to_raw, str) else None
                if not reply_to:
                    reply_to = default_profile["reply_to"]
                return {
                    "from_name": from_name,
                    "from_address": from_address,
                    "reply_to": reply_to,
                }
        return default_profile

    def _load_sender_profiles_from_file(self, file_path: str | None) -> dict[str, SenderProfile]:
        if not file_path:
            return {}

        resolved_path = Path(file_path)
        if not resolved_path.is_absolute():
            try:
                repo_root = Path(__file__).resolve().parents[3]
            except IndexError:  # pragma: no cover - defensive fallback
                repo_root = Path.cwd()
            resolved_path = (repo_root / resolved_path).resolve()

        if not resolved_path.exists():
            self._log_sender_profile_warning(f"Sender profiles file not found: {resolved_path}")
            return {}

        try:
            raw = resolved_path.read_text(encoding="utf-8")
        except OSError as exc:  # pragma: no cover - filesystem edge cases
            self._log_sender_profile_warning(
                f"Failed to read sender profiles file {resolved_path}: {exc}"
            )
            return {}

        parsed = self._parse_sender_profiles(raw, allow_partial=False)
        result: dict[str, SenderProfile] = {}
        for key, value in parsed.items():
            profile: SenderProfile = {
                "from_name": value.get("from_name", ""),
                "from_": value.get("from_", ""),
            }
            reply_to_value = value.get("reply_to")
            if reply_to_value:
                profile["reply_to"] = reply_to_value
            result[key] = profile
        return result

    def _parse_sender_profiles(
        self, raw: str | None, *, allow_partial: bool
    ) -> dict[str, dict[str, str]]:
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:  # pragma: no cover - log and ignore invalid env
            self._log_sender_profile_warning(f"Failed to parse EMAIL_SENDER_PROFILES_JSON: {exc}")
            return {}
        if not isinstance(data, dict):
            self._log_sender_profile_warning(
                "EMAIL_SENDER_PROFILES_JSON must decode to an object mapping"
            )
            return {}

        parsed: dict[str, dict[str, str]] = {}
        for key, value in data.items():
            if not isinstance(key, str) or not isinstance(value, dict):
                logger.debug("Skipping invalid sender profile entry: %s", key)
                continue
            from_name = value.get("from_name")
            from_address = value.get("from") or value.get("from_")
            reply_to_value = value.get("reply_to")

            profile: dict[str, str] = {}
            if isinstance(from_name, str) and from_name.strip():
                profile["from_name"] = from_name.strip()
            elif isinstance(from_name, str) and allow_partial:
                profile["from_name"] = from_name.strip()

            if isinstance(from_address, str) and from_address.strip():
                profile["from_"] = from_address.strip()
            elif isinstance(from_address, str) and allow_partial:
                profile["from_"] = from_address.strip()

            if isinstance(reply_to_value, str):
                cleaned_reply = reply_to_value.strip()
                if cleaned_reply or allow_partial:
                    profile["reply_to"] = cleaned_reply

            if not allow_partial and ("from_name" not in profile or "from_" not in profile):
                logger.debug("Sender profile %s missing required fields", key)
                continue

            if profile:
                parsed[key] = profile
        return parsed

    def _default_sender_profile(self) -> SenderProfileResolved:
        name = (self.email_from_name or "").strip()
        address = (self.email_from_address or "").strip()

        parsed_name, parsed_address = parseaddr(self.from_email)
        if not name:
            name = parsed_name.strip() if parsed_name else BRAND_NAME
        if not address:
            address = parsed_address or "hello@instainstru.com"

        reply_to = (self.email_reply_to or "").strip()
        return {
            "from_name": name,
            "from_address": address,
            "reply_to": reply_to or None,
        }

    def _log_sender_profile_warning(self, message: str) -> None:
        if not self._sender_profiles_warning_logged:
            logger.warning(message)
            self._sender_profiles_warning_logged = True


def assert_env(
    site_mode_raw: str,
    checkr_env: str,
    *,
    fake: bool | None = None,
    allow_override: bool | None = None,
) -> None:
    """Apply Checkr environment guardrails based on SITE_MODE and toggles."""

    normalized_site_mode, is_prod, is_non_prod = _classify_site_mode(site_mode_raw)
    normalized_checkr_env = (checkr_env or "").strip().lower()

    if fake is None:
        effective_fake = settings.checkr_fake if not is_prod else False
    else:
        effective_fake = fake

    effective_override = (
        settings.allow_sandbox_checkr_in_prod if allow_override is None else allow_override
    )

    if is_prod:
        if normalized_checkr_env == "production":
            return
        if normalized_checkr_env == "sandbox" and (effective_fake or effective_override):
            logger.warning("Permitting CHECKR_ENV=sandbox in production due to FakeCheckr/override")
            return
        raise RuntimeError("Refusing to start: production requires CHECKR_ENV=production")

    if is_non_prod:
        if normalized_checkr_env == "sandbox":
            return
        raise RuntimeError("Refusing to start: non-prod requires CHECKR_ENV=sandbox")

    if normalized_checkr_env == "sandbox":
        return

    # Treat everything outside PROD bucket as non-prod for safety.
    raise RuntimeError("Refusing to start: non-prod requires CHECKR_ENV=sandbox")


settings = Settings()
logger.info(
    "[CONFIG] Background check configuration: site_mode=%s checkr_env=%s checkr_fake=%s",
    settings.site_mode,
    settings.checkr_env,
    settings.checkr_fake,
)
