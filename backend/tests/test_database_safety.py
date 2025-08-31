"""Test that database safety cannot be bypassed."""

import os
from unittest.mock import patch

import pytest


def test_default_is_int_database():
    """Default database must be INT."""
    # Clear any env vars
    os.environ.pop("SITE_MODE", None)

    # Mock CI detection to ensure we're not in CI mode for this test
    with patch("app.core.database_config.DatabaseConfig._is_ci_environment", return_value=False):
        # Create fresh DatabaseConfig to test
        from app.core.database_config import DatabaseConfig

        config = DatabaseConfig()

        url = config.get_database_url()
        assert "instainstru_test" in url, f"Expected INT database, got {url}"


def test_cannot_access_prod_without_confirmation():
    """Production database requires confirmation in non-interactive mode."""
    # Save and clear DATABASE_URL to ensure CI doesn't interfere
    db_url = os.environ.pop("DATABASE_URL", None)
    os.environ["SITE_MODE"] = "prod"

    try:
        # Mock CI detection and production server mode to ensure confirmation path
        with patch("app.core.database_config.DatabaseConfig._is_ci_environment", return_value=False), patch(
            "app.core.database_config.DatabaseConfig._check_production_mode", return_value=False
        ):
            # Create fresh DatabaseConfig to test
            from app.core.database_config import DatabaseConfig

            config = DatabaseConfig()

            # In non-interactive mode (like tests), this should raise RuntimeError
            with pytest.raises(RuntimeError, match="Production database access requested in non-interactive mode"):
                _ = config.get_database_url()
    finally:
        # Cleanup
        os.environ.pop("SITE_MODE", None)
        if db_url:
            os.environ["DATABASE_URL"] = db_url


def test_old_scripts_safe_by_default():
    """Old patterns must be safe."""
    # Clear any env vars
    os.environ.pop("SITE_MODE", None)

    # Mock CI detection
    with patch("app.core.database_config.DatabaseConfig._is_ci_environment", return_value=False):
        # Create fresh DatabaseConfig to test
        from app.core.database_config import DatabaseConfig

        config = DatabaseConfig()

        # Even direct access should be safe
        url = config.get_database_url()
        assert "instainstru_test" in url, f"Old patterns should default to INT, got {url}"


def test_stg_database_with_flag():
    """Staging database accessible with flag."""
    # Save and clear DATABASE_URL to prevent CI interference
    db_url = os.environ.pop("DATABASE_URL", None)
    os.environ["SITE_MODE"] = "local"

    try:
        # Mock CI detection to ensure consistent behavior
        with patch("app.core.database_config.DatabaseConfig._is_ci_environment", return_value=False):
            # Create fresh DatabaseConfig to test
            from app.core.database_config import DatabaseConfig

            config = DatabaseConfig()

            # Check if STG database is actually configured
            # In some environments, stg_database_url might not be set
            if not config.stg_url or config.stg_url == config.prod_url:
                # Skip this test if STG is not properly configured
                import pytest

                pytest.skip("STG database URL not configured in this environment")

            url = config.get_database_url()
            assert url == config.stg_url, f"Expected STG database URL {config.stg_url}, got {url}"
    finally:
        # Cleanup
        os.environ.pop("SITE_MODE", None)
        if db_url:
            os.environ["DATABASE_URL"] = db_url


def test_backward_compatibility():
    """test_database_url property should work."""
    # No need to mock CI for this test as test_database_url always returns INT
    from app.core.config import settings

    url = settings.test_database_url
    assert "instainstru_test" in url, f"test_database_url should return INT, got {url}"


def test_raw_fields_not_in_public_api():
    """Raw database URL fields should not be easily discoverable."""
    from app.core.config import settings

    # The raw fields exist but are marked as internal
    assert hasattr(settings, "prod_database_url_raw")
    assert hasattr(settings, "int_database_url_raw")
    assert hasattr(settings, "stg_database_url_raw")

    # But the main API uses safe properties
    assert hasattr(settings, "database_url")
    assert hasattr(settings, "test_database_url")
    assert hasattr(settings, "stg_database_url")


def test_alembic_uses_safe_database():
    """Alembic should use INT database by default."""
    # Clear any env vars
    os.environ.pop("SITE_MODE", None)

    # We can't actually run alembic in tests, but we can check
    # that settings.database_url returns INT
    from app.core.config import settings

    assert "instainstru_test" in settings.database_url


def test_production_server_can_access_prod():
    """Production servers should be able to access production database."""
    # SITE_MODE=prod should allow production server access when production mode detected
    os.environ["SITE_MODE"] = "prod"

    try:
        from app.core.config import settings

        # This should NOT raise an error in production mode
        with patch("app.core.database_config.DatabaseConfig._check_production_mode", return_value=True):
            url = settings.database_url
        # In test environment, we won't actually get prod URL
        # but we should not get an error
        assert url is not None
    finally:
        # Cleanup
        os.environ.pop("SITE_MODE", None)


def test_production_requires_production_server_mode():
    """Without production server mode, SITE_MODE=prod should require confirmation and fail in non-interactive tests."""
    os.environ["SITE_MODE"] = "prod"

    from app.core.database_config import DatabaseConfig

    with patch("app.core.database_config.DatabaseConfig._is_ci_environment", return_value=False), patch(
        "app.core.database_config.DatabaseConfig._check_production_mode", return_value=False
    ):
        config = DatabaseConfig()
        with pytest.raises(RuntimeError, match="non-interactive mode"):
            _ = config.get_database_url()


def test_local_prod_requires_confirmation():
    """Local production access should still require confirmation even with USE_PROD_DATABASE."""
    # Set SITE_MODE=prod but not production server mode
    os.environ["SITE_MODE"] = "prod"
    os.environ.pop("RENDER", None)

    try:
        # Mock both CI detection and production mode detection
        with patch("app.core.database_config.DatabaseConfig._is_ci_environment", return_value=False), patch(
            "app.core.database_config.DatabaseConfig._check_production_mode", return_value=False
        ):
            # Create fresh DatabaseConfig to test
            from app.core.database_config import DatabaseConfig

            config = DatabaseConfig()

            # In non-interactive mode (tests), this should raise
            with pytest.raises(RuntimeError, match="non-interactive mode"):
                _ = config.get_database_url()
    finally:
        # Cleanup
        os.environ.pop("SITE_MODE", None)


def test_ci_environment_detection():
    """Test that CI environments are properly detected."""
    # Save original DATABASE_URL if it exists
    db_url = os.environ.pop("DATABASE_URL", None)

    # Set CI indicator
    os.environ["CI"] = "true"

    try:
        from app.core.database_config import DatabaseConfig

        config = DatabaseConfig()
        # Should detect CI environment
        assert config._is_ci_environment() is True

        # CI should default to INT database if no DATABASE_URL
        url = config.get_database_url()
        assert "instainstru_test" in url
    finally:
        # Cleanup
        os.environ.pop("CI", None)
        if db_url:
            os.environ["DATABASE_URL"] = db_url


def test_ci_uses_provided_database():
    """CI should use DATABASE_URL when provided."""
    # Save original DATABASE_URL if it exists
    original_db_url = os.environ.get("DATABASE_URL")

    # Set CI environment and custom DATABASE_URL
    os.environ["CI"] = "true"
    os.environ["DATABASE_URL"] = "postgresql://ci_user:ci_pass@localhost/ci_test_db"

    try:
        from app.core.config import settings

        # Should use the CI-provided DATABASE_URL
        url = settings.database_url
        assert "ci_test_db" in url
    finally:
        # Cleanup
        os.environ.pop("CI", None)
        if original_db_url:
            os.environ["DATABASE_URL"] = original_db_url
        else:
            os.environ.pop("DATABASE_URL", None)


def test_ci_without_database_uses_int():
    """CI without DATABASE_URL should default to INT."""
    # Save original DATABASE_URL if it exists
    db_url = os.environ.pop("DATABASE_URL", None)

    # Set CI but no DATABASE_URL
    os.environ["CI"] = "true"

    try:
        from app.core.config import settings

        # Should default to INT database
        url = settings.database_url
        assert "instainstru_test" in url
    finally:
        # Cleanup
        os.environ.pop("CI", None)
        if db_url:
            os.environ["DATABASE_URL"] = db_url


def test_production_mode_overrides_ci():
    """Production mode should take precedence over CI mode."""
    # Set both CI and production flags
    os.environ["CI"] = "true"
    os.environ["SITE_MODE"] = "prod"

    try:
        from app.core.config import settings

        # Should use production database (in production mode, no confirmation needed)
        # In test environment, this should not raise an error
        with patch("app.core.database_config.DatabaseConfig._check_production_mode", return_value=True):
            url = settings.database_url
        assert url is not None
    finally:
        # Cleanup
        os.environ.pop("CI", None)
        os.environ.pop("SITE_MODE", None)
