# backend/app/core/config.py
import logging
import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import ConfigDict, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

# Load .env file only if not in CI
if not os.getenv("CI"):
    env_path = Path(__file__).parent.parent.parent / ".env"  # Goes up to backend/.env
    logger.info(f"[CONFIG] Looking for .env at: {env_path}")
    logger.info(f"[CONFIG] .env exists: {env_path.exists()}")
    logger.info(f"[CONFIG] Absolute path: {env_path.absolute()}")
    load_dotenv(env_path)


class Settings(BaseSettings):
    secret_key: SecretStr
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    database_url: str

    # Test database configuration
    test_database_url: str = ""  # Must be explicitly set for tests
    is_testing: bool = False  # Set to True when running tests

    # Email settings
    resend_api_key: str = ""
    from_email: str = "noreply@instainstru.com"
    admin_email: str = "msaedi@berkeley.edu"  # Email for critical alerts

    # Frontend URL - will use production URL if not set
    frontend_url: str = "https://instructly-ten.vercel.app"

    # Environment
    environment: str = "production"  # or "development"

    # Cache settings
    redis_url: str = "redis://localhost:6379"
    cache_ttl: int = 3600  # 1 hour in seconds

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
    model_config = ConfigDict(
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
        default=300, description="Cache TTL in seconds for public availability data"  # 5 minutes
    )

    # Rate Limiting Configuration
    rate_limit_enabled: bool = Field(default=True, description="Enable rate limiting (disable for testing)")

    rate_limit_general_per_minute: int = Field(default=100, description="General API rate limit per minute per IP")

    rate_limit_auth_per_minute: int = Field(default=5, description="Authentication attempts per minute per IP")

    rate_limit_password_reset_per_hour: int = Field(default=3, description="Password reset requests per hour per email")

    rate_limit_password_reset_ip_per_hour: int = Field(
        default=10, description="Password reset requests per hour per IP"
    )

    rate_limit_register_per_hour: int = Field(default=10, description="Registration attempts per hour per IP")

    rate_limit_booking_per_minute: int = Field(default=20, description="Booking requests per minute per user")

    rate_limit_expensive_per_minute: int = Field(default=10, description="Expensive operations per minute per user")

    # Rate limit bypass for testing
    rate_limit_bypass_token: str = Field(default="", description="Token to bypass rate limiting (for load testing)")

    # Template Caching Configuration
    template_cache_enabled: bool = Field(
        default=True, description="Enable template service caching (disable for development if needed)"
    )

    @field_validator("test_database_url")
    @classmethod
    def validate_test_database(cls, v: str, info) -> str:
        """Ensure test database is not a production database."""
        if not v:
            return v

        # Get the list of production indicators from the values
        prod_indicators = info.data.get("production_database_indicators", [])

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
                "Test database URL doesn't contain 'test' in its name. " "Consider using a clearly named test database."
            )

        return v

    def get_database_url(self) -> str:
        """Get the appropriate database URL based on context."""
        # If we're explicitly in testing mode and have a test database URL
        if self.is_testing and self.test_database_url:
            return self.test_database_url

        # If we're testing but no test database is configured
        if self.is_testing:
            raise ValueError(
                "Testing mode is enabled but TEST_DATABASE_URL is not configured. "
                "Please set TEST_DATABASE_URL in your environment."
            )

        # Production mode - return normal database URL
        return self.database_url

    def is_production_database(self, url: str = None) -> bool:
        """Check if a database URL appears to be a production database."""
        check_url = url or self.database_url
        return any(indicator in check_url.lower() for indicator in self.production_database_indicators)


settings = Settings()
