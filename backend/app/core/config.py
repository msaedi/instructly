# backend/app/core/config.py
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Literal, Optional, cast

if TYPE_CHECKING:
    load_dotenv: Callable[..., bool]
try:
    from dotenv import load_dotenv as _real_load_dotenv

    load_dotenv = cast(Callable[..., bool], _real_load_dotenv)
except Exception:  # pragma: no cover - optional on CI

    def load_dotenv(*_args: Any, **_kwargs: Any) -> bool:
        return False


from pydantic import Field, SecretStr, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Load .env file only if not in CI
if not os.getenv("CI"):
    env_path = Path(__file__).parent.parent.parent / ".env"  # Goes up to backend/.env
    logger.info(f"[CONFIG] Looking for .env at: {env_path}")
    logger.info(f"[CONFIG] .env exists: {env_path.exists()}")
    logger.info(f"[CONFIG] Absolute path: {env_path.absolute()}")
    load_dotenv(env_path)


PRODUCTION_SITE_MODES = {"prod", "production", "live"}


class Settings(BaseSettings):
    # Use a default secret key for CI/testing environments
    secret_key: SecretStr = Field(
        default=cast(
            object,
            SecretStr("ci-test-secret-key-not-for-production") if os.getenv("CI") else ...,
        ),
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

    # Raw database URLs - DO NOT USE DIRECTLY! Use properties instead
    # Explicit env names (no backward compatibility):
    #  - prod_database_url
    #  - preview_database_url
    #  - stg_database_url
    #  - test_database_url
    prod_database_url_raw: Optional[str] = Field(
        default=None, alias="prod_database_url"
    )  # From env PROD_DATABASE_URL
    preview_database_url_raw: str = Field(
        default="", alias="preview_database_url"
    )  # From env PREVIEW_DATABASE_URL
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
    resend_api_key: str = ""
    from_email: str = "InstaInstru <hello@instainstru.com>"
    admin_email: str = "admin@instainstru.com"  # Email for critical alerts

    # Frontend URL - will use production URL if not set
    frontend_url: str = "https://beta.instainstru.com"
    identity_return_path: str = "/instructor/onboarding/verification?identity_return=true"
    local_beta_frontend_origin: str = Field(
        default="http://beta-local.instainstru.com:3000",
        description="Local-only override for beta invite links",
    )
    frontend_referral_landing_url: str = Field(
        default="https://beta.instainstru.com/referrals",
        description="Landing page for public referral links",
    )

    # Environment (derived from SITE_MODE)
    environment: str = (
        "production"
        if os.getenv("SITE_MODE", "local").lower() in {"prod", "production", "live"}
        else "development"
    )

    # Checkr configuration
    checkr_env: str = Field(
        default="sandbox",
        description="Target Checkr environment (sandbox|production)",
    )
    checkr_api_key: SecretStr = Field(
        default=SecretStr(""),
        description="Checkr API key for background check operations",
    )
    checkr_package: str = Field(
        default="essential",
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

    @property
    def site_mode(self) -> Literal["local", "preview", "prod"]:
        """Return canonical site mode derived from SITE_MODE."""
        raw_mode = os.getenv("SITE_MODE", "").strip().lower()
        if raw_mode == "preview":
            return "preview"
        if raw_mode in {"prod", "production", "live"}:
            return "prod"
        return "local"

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

    # Rate Limiting Configuration
    rate_limit_enabled: bool = Field(
        default=True, description="Enable rate limiting (disable for testing)"
    )

    rate_limit_general_per_minute: int = Field(
        default=100, description="General API rate limit per minute per IP"
    )

    rate_limit_auth_per_minute: int = Field(
        default=5, description="Authentication attempts per minute per IP"
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


def assert_env(site_mode: str, checkr_env: str) -> None:
    """Abort startup when Checkr configuration does not match the SITE_MODE."""

    normalized_site_mode = (site_mode or "").strip().lower()
    normalized_checkr_env = (checkr_env or "").strip().lower()

    if normalized_site_mode in PRODUCTION_SITE_MODES:
        if normalized_checkr_env != "production":
            raise RuntimeError("Refusing to start: production requires CHECKR_ENV=production")
    else:
        if normalized_checkr_env != "sandbox":
            raise RuntimeError("Refusing to start: non-prod requires CHECKR_ENV=sandbox")


settings = Settings()
