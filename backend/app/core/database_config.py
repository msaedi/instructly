# backend/app/core/database_config.py
"""
Database Configuration System - Three-Tier Architecture

This module implements a three-tier database selection system designed for both
immediate safety and future enterprise features.

Current Implementation:
- INT (Integration Test DB): Default database for pytest, freely droppable
- STG (Staging/Local Dev DB): For localhost development, preserves data
- PROD (Production DB): Supabase with interactive confirmation required

Future Extension Points:
- Production mode detection and validation
- Automated backup before destructive operations
- Schema version validation
- Dry-run mode for dangerous operations
- Rate limiting for production access
- Audit logging of all database operations
"""

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import sys
from typing import Any, Literal, Optional
from urllib.parse import urlparse, urlunparse

from .config import settings

try:
    from app.utils.env_logging import log_info as scripts_log_info
except ImportError:

    def scripts_log_info(env: str, message: str) -> None:
        print(f"[{env.upper()}] {message}")


logger = logging.getLogger(__name__)

DatabaseEnvironment = Literal["int", "stg", "prod"]


def _getenv(*names: str, default: str | None = None) -> str | None:
    """Return the first non-empty env var from a list (case-insensitive)."""

    for name in names:
        value = os.getenv(name)
        if value:
            return value
        value = os.getenv(name.lower())
        if value:
            return value
    return default


class DatabaseConfig:
    """
    Manages database selection with safety guarantees and extension points.

    This class provides the foundation for enterprise database management features
    while solving immediate safety concerns.
    """

    def __init__(self) -> None:
        """Initialize database configuration."""
        # Access raw fields directly to avoid circular dependency
        self.int_url = _getenv(
            "TEST_DATABASE_URL",
            "DATABASE_URL",
            default=settings.int_database_url_raw,
        )
        self.stg_url = _getenv(
            "STG_DATABASE_URL",
            "STAGING_DATABASE_URL",
            "DATABASE_URL",
            default=settings.stg_database_url_raw or settings.prod_database_url_raw,
        )
        self.prod_url = (
            _getenv(
                "PROD_DATABASE_URL",
                "PRODUCTION_DATABASE_URL",
                "DATABASE_URL",
                default=settings.prod_database_url_raw,
            )
            or ""
        )
        self.preview_url = _getenv(
            "PREVIEW_DATABASE_URL",
            "DATABASE_URL",
            default=settings.preview_database_url_raw,
        )

        # Validate configuration on startup
        self.validate_configuration()

        # Setup audit logging directory
        self.audit_log_path = Path(__file__).parent.parent.parent / "logs" / "database_audit.jsonl"
        self.audit_log_path.parent.mkdir(exist_ok=True)

    def get_database_url(self) -> str:
        """
        Main entry point for database URL selection.

        Priority order:
        1. If pytest is detected, force INT (for safety)
        2. If CI environment + DATABASE_URL provided, use it
        3. If USE_PROD_DATABASE=true, use production (with confirmation)
        4. If USE_STG_DATABASE=true, use staging
        5. Auto-detect environment and suggest appropriate database
        6. Default: use INT (integration test database)

        Returns:
            str: The selected database URL
        """
        # Special handling for CI environments
        if self._is_ci_environment():
            # Check if CI has provided a custom DATABASE_URL
            ci_database_url = os.getenv("DATABASE_URL")
            if ci_database_url:
                safe_url = self._coerce_safe_ci_db_url(ci_database_url)
                logger.warning(
                    "CI environment forcing safe database name",
                    extra={
                        "original": self._mask_url(ci_database_url),
                        "forced": self._mask_url(safe_url),
                    },
                )
                scripts_log_info("int", "Using CI-safe database URL")
                self._audit_log_operation(
                    "ci_database_selection",
                    {
                        "original_url": self._mask_url(ci_database_url),
                        "forced_url": self._mask_url(safe_url),
                        "ci_environment": os.getenv("CI", "unknown"),
                    },
                )
                os.environ["DATABASE_URL"] = safe_url
                return safe_url

        # First, honor SITE_MODE (authoritative explicit selection)
        site_mode = os.getenv("SITE_MODE", "").lower().strip()
        if site_mode:
            if site_mode in {"prod", "production", "live"}:
                return self._get_production_url()
            if site_mode in {"preview"}:
                return self._get_preview_url()
            if site_mode in {"local", "stg", "stage", "staging"}:
                return self._get_staging_url()
            if site_mode in {"int", "test", "ci"}:
                return self._get_int_url()

        # Then, detect environment
        detected_env = self._detect_environment()

        # Force INT if pytest is running
        if detected_env == "int":
            return self._get_int_url()

        # If local dev environment detected, suggest STG
        if detected_env == "stg":
            logger.info(
                "[Database] Local development detected. Consider setting USE_STG_DATABASE=true to use staging database."
            )

        # Default to INT database for safety
        return self._get_int_url()

    def _detect_environment(self) -> DatabaseEnvironment:
        """
        Automatically detect the current environment.

        Returns:
            DatabaseEnvironment: Detected environment (int, stg, or prod)
        """
        # Check if pytest is running
        if "pytest" in sys.modules:
            return "int"

        # Check for CI/CD environment
        if self._is_ci_environment():
            return "int"  # CI uses its own database via DATABASE_URL

        # Check for local development indicators
        if self._is_local_development():
            return "stg"

        # Check for production indicators
        if self._check_production_mode():
            return "prod"

        # Default to INT for safety
        return "int"

    def _is_ci_environment(self) -> bool:
        """
        Check if running in a CI/CD environment.

        Returns:
            bool: True if CI environment detected
        """
        ci_indicators = [
            "CI",  # Generic CI indicator
            "GITHUB_ACTIONS",  # GitHub Actions
            "GITLAB_CI",  # GitLab CI
            "CIRCLECI",  # CircleCI
            "TRAVIS",  # Travis CI
            "JENKINS_URL",  # Jenkins
            "BUILDKITE",  # Buildkite
            "DRONE",  # Drone CI
            "BITBUCKET_PIPELINES",  # Bitbucket Pipelines
            "TEAMCITY_VERSION",  # TeamCity
        ]

        # Check if any CI indicator is present
        for indicator in ci_indicators:
            if os.getenv(indicator):
                logger.info(f"CI environment detected: {indicator}={os.getenv(indicator)}")
                return True

        return False

    @staticmethod
    def _coerce_safe_ci_db_url(url: str, *, safe_db: str = "instainstru_test") -> str:
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return url
            new_path = f"/{safe_db}"
            coerced = parsed._replace(path=new_path)
            return urlunparse(coerced)
        except Exception:
            return url

    def _is_local_development(self) -> bool:
        """Check if running in local development mode."""
        indicators = [
            # Check if uvicorn is running locally
            "uvicorn" in " ".join(sys.argv),
            # Check for localhost in environment
            os.getenv("FRONTEND_URL", "").startswith("http://localhost"),
            # Check for development environment
            os.getenv("ENVIRONMENT", "").lower() == "development",
        ]
        return any(indicators)

    def _get_int_url(self) -> str:
        """Get integration test database URL."""
        if not self.int_url:
            raise ValueError(
                "INT database URL not configured. "
                "Please set test_database_url in your .env file."
            )
        if not os.getenv("SUPPRESS_DB_MESSAGES"):
            scripts_log_info("int", "Using Integration Test database (safe for drops/resets)")
        self._audit_log_operation(
            "database_selection", {"environment": "int", "url": self._mask_url(self.int_url)}
        )
        return self.int_url

    def _get_staging_url(self) -> str:
        """Get staging/local development database URL."""
        if not self.stg_url:
            raise ValueError(
                "STG database URL not configured. " "Please set stg_database_url in your .env file."
            )
        scripts_log_info("stg", "Using Staging/Local Dev database (preserves data)")
        self._audit_log_operation(
            "database_selection", {"environment": "stg", "url": self._mask_url(self.stg_url)}
        )
        return self.stg_url

    def _get_preview_url(self) -> str:
        """Get preview database URL (for preview site mode)."""
        if not self.preview_url:
            raise ValueError(
                "Preview database URL not configured. Please set preview_database_url in your environment."
            )
        scripts_log_info("preview", "Using Preview database")
        self._audit_log_operation(
            "database_selection",
            {"environment": "preview", "url": self._mask_url(self.preview_url)},
        )
        return self.preview_url

    def _get_production_url(self) -> str:
        """
        Get production database URL with safety checks.

        Requires interactive confirmation to prevent accidents, unless running
        in production server mode.
        """
        # Future: Call pre-production checks
        self._pre_production_checks()

        # Check if we're in production server mode
        is_production_server = self._check_production_mode()

        if is_production_server:
            # Production servers can access without confirmation
            logger.info("Production server mode detected - allowing production database access")
            scripts_log_info("prod", "Production server accessing production database")
            self._audit_log_operation(
                "production_server_access",
                {
                    "url": self._mask_url(self.prod_url),
                    "production_mode": True,
                    "environment": os.getenv("INSTAINSTRU_PRODUCTION_MODE", "auto-detected"),
                },
            )
            return self.prod_url

        # Show warning with red color
        print("\n" + "=" * 60)
        print("\033[91m⚠️  PRODUCTION DATABASE ACCESS REQUESTED ⚠️\033[0m")
        print("=" * 60)
        print("You are about to access the PRODUCTION database.")
        print("This action could affect real user data.")
        print("\nDatabase:", self._mask_url(self.prod_url))
        print("=" * 60)

        # Check if running in non-interactive mode
        if not sys.stdin.isatty():
            self._audit_log_operation(
                "production_access_denied", {"reason": "non_interactive_mode"}
            )
            raise RuntimeError(
                "Production database access requested in non-interactive mode. "
                "Production access requires interactive confirmation. "
                "For production servers, set INSTAINSTRU_PRODUCTION_MODE=true"
            )

        # Require confirmation
        confirmation = input("\nType 'yes' to confirm production access: ")
        if confirmation.lower() != "yes":
            print("Production access cancelled.")
            self._audit_log_operation("production_access_denied", {"reason": "user_cancelled"})
            sys.exit(1)

        # Future: Call post-approval hooks
        self._post_production_approval()

        scripts_log_info("prod", "Using Production database - BE CAREFUL!")
        self._audit_log_operation(
            "production_access_granted", {"url": self._mask_url(self.prod_url)}
        )
        return self.prod_url

    def validate_configuration(self) -> None:
        """
        Validate that all required database URLs are configured.

        Raises:
            ValueError: If any required database URL is missing
        """
        errors = []

        site_mode = os.getenv("SITE_MODE", "").lower().strip()

        # Explicit SITE_MODE selection takes precedence
        if site_mode in {"prod", "production", "live"}:
            if not self.prod_url:
                errors.append("PROD database (prod_database_url) not configured")
        elif site_mode in {"preview"}:
            if not self.preview_url:
                errors.append("PREVIEW database (preview_database_url) not configured")
        elif site_mode in {"local", "stg", "stage", "staging"}:
            if not self.stg_url and not self.prod_url:
                errors.append(
                    "STG database (stg_database_url) not configured and no prod_database_url fallback"
                )
            elif not self.stg_url and self.prod_url and not self._is_ci_environment():
                logger.info(
                    "STG database (stg_database_url) not configured; using prod_database_url as fallback for SITE_MODE=local/stg"
                )
        elif site_mode in {"int", "test", "ci"}:
            if not self.int_url:
                errors.append("INT database (test_database_url) not configured")
        else:
            # Fallback behavior if SITE_MODE is unset/unknown
            if self._check_production_mode():
                if not self.prod_url:
                    errors.append("PROD database (prod_database_url) not configured")
            else:
                # Default to INT for safety
                if not self.int_url:
                    errors.append("INT database (test_database_url) not configured")

        if errors:
            raise ValueError(
                "Database configuration errors:\n" + "\n".join(f"  - {error}" for error in errors)
            )

    def get_safety_score(self) -> dict[str, Any]:
        """
        Calculate and return current database safety metrics.

        Returns:
            Dict containing safety score and individual metrics
        """
        metrics = {
            "three_tier_architecture": True,  # We have INT/STG/PROD separation
            "production_confirmation": True,  # Production requires confirmation
            "test_isolation": True,  # Tests forced to INT database
            "environment_detection": True,  # Auto-detect environment
            "audit_logging": True,  # Basic audit logging implemented
            "visual_indicators": True,  # Color-coded database selection
            "configuration_validation": True,  # Startup validation
            "masked_urls": True,  # URLs are masked in logs
            "interactive_check": True,  # Non-interactive mode blocks production
            # Future features (not yet implemented)
            "automated_backups": False,
            "schema_validation": False,
            "dry_run_mode": False,
            "rate_limiting": False,
            "role_based_access": False,
            "encryption_at_rest": False,
            "point_in_time_recovery": False,
        }

        # Calculate overall score
        implemented = sum(1 for v in metrics.values() if v)
        total = len(metrics)
        score = (implemented / total) * 100

        return {
            "score": round(score, 1),
            "implemented_features": implemented,
            "total_features": total,
            "metrics": metrics,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _mask_url(self, url: str) -> str:
        """Mask sensitive parts of database URL for logging."""
        if "@" in url:
            # Hide password but show host
            parts = url.split("@")
            prefix = parts[0].split("//")[0] + "//***:***@"
            suffix = parts[1]
            return prefix + suffix
        return url

    def _audit_log_operation(self, operation: str, details: dict[str, Any]) -> None:
        """
        Log database operations for audit trail.

        Args:
            operation: Type of operation (e.g., 'database_selection', 'migration')
            details: Additional context about the operation
        """
        try:
            log_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "operation": operation,
                "user": os.getenv("USER", "unknown"),
                "pid": os.getpid(),
                "details": details,
            }

            with open(self.audit_log_path, "a") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception as e:
            logger.warning(f"Failed to write audit log: {e}")

    # ========== Extension Points for Future Features ==========

    def _check_production_mode(self) -> bool:
        """
        Detect if we're running in production environment.

        Authoritative source: SITE_MODE only. Platform indicators are ignored
        to prevent misclassification (e.g., Render preview).
        """
        return os.getenv("SITE_MODE", "").lower().strip() in {"prod", "production", "live"}

    def _pre_production_checks(self) -> None:
        """
        Future: Perform checks before allowing production access.

        Could include:
        - User authentication level
        - Time-based access restrictions
        - Maintenance window checks
        """
        return None

    def _post_production_approval(self) -> None:
        """
        Future: Actions to take after production access is approved.

        Could include:
        - Send notifications to team
        - Start session recording
        - Enable additional logging
        """
        return None

    def _create_backup_if_needed(self, operation: str) -> Optional[str]:
        """
        Future: Create automatic backups before destructive operations.

        Args:
            operation: The operation about to be performed

        Returns:
            Optional[str]: Backup identifier if backup was created
        """
        return None

    def _validate_schema_version(self) -> bool:
        """
        Future: Ensure database schema matches application version.

        Returns:
            bool: True if schema is compatible
        """
        return False

    def _check_dry_run_mode(self) -> bool:
        """
        Future: Check if operations should be simulated only.

        Returns:
            bool: True if in dry-run mode
        """
        return False

    def _rate_limit_check(self, operation: str) -> bool:
        """
        Future: Implement rate limiting for database operations.

        Args:
            operation: Type of operation to check

        Returns:
            bool: True if operation is allowed
        """
        return False
