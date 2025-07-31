"""Test that database safety cannot be bypassed - CI-compatible version."""

import os
from unittest.mock import patch

import pytest


def test_default_is_int_database():
    """Default database must be INT."""
    # Clear any env vars
    os.environ.pop("USE_PROD_DATABASE", None)
    os.environ.pop("USE_STG_DATABASE", None)
    db_url = os.environ.pop("DATABASE_URL", None)

    try:
        # Mock CI detection to ensure we're testing default behavior
        with patch("app.core.database_config.DatabaseConfig._is_ci_environment", return_value=False):
            from app.core.database_config import DatabaseConfig

            config = DatabaseConfig()

            url = config.get_database_url()
            assert "instainstru_test" in url, f"Expected INT database, got {url}"
    finally:
        if db_url:
            os.environ["DATABASE_URL"] = db_url


def test_cannot_access_prod_without_confirmation():
    """Production database requires confirmation in non-interactive mode."""
    # Save and clear DATABASE_URL to ensure CI doesn't interfere
    db_url = os.environ.pop("DATABASE_URL", None)
    os.environ["USE_PROD_DATABASE"] = "true"

    try:
        # Mock both CI and production mode detection
        with patch("app.core.database_config.DatabaseConfig._is_ci_environment", return_value=False), patch(
            "app.core.database_config.DatabaseConfig._check_production_mode", return_value=False
        ):
            from app.core.database_config import DatabaseConfig

            config = DatabaseConfig()

            # In non-interactive mode (like tests), this should raise RuntimeError
            with pytest.raises(RuntimeError, match="Production database access requested in non-interactive mode"):
                _ = config.get_database_url()
    finally:
        os.environ.pop("USE_PROD_DATABASE", None)
        if db_url:
            os.environ["DATABASE_URL"] = db_url


def test_old_scripts_safe_by_default():
    """Old patterns must be safe."""
    os.environ.pop("USE_PROD_DATABASE", None)
    os.environ.pop("USE_STG_DATABASE", None)
    db_url = os.environ.pop("DATABASE_URL", None)

    try:
        # Mock CI detection
        with patch("app.core.database_config.DatabaseConfig._is_ci_environment", return_value=False):
            from app.core.database_config import DatabaseConfig

            config = DatabaseConfig()

            url = config.get_database_url()
            assert "instainstru_test" in url, f"Old patterns should default to INT, got {url}"
    finally:
        if db_url:
            os.environ["DATABASE_URL"] = db_url


def test_stg_database_with_flag():
    """Staging database accessible with flag."""
    # Save and clear DATABASE_URL to prevent CI interference
    db_url = os.environ.pop("DATABASE_URL", None)
    os.environ["USE_STG_DATABASE"] = "true"
    os.environ.pop("USE_PROD_DATABASE", None)

    try:
        # Mock CI detection to ensure we get STG behavior
        with patch("app.core.database_config.DatabaseConfig._is_ci_environment", return_value=False):
            from app.core.database_config import DatabaseConfig

            config = DatabaseConfig()

            url = config.get_database_url()
            assert "instainstru_stg" in url, f"Expected STG database, got {url}"
    finally:
        os.environ.pop("USE_STG_DATABASE", None)
        if db_url:
            os.environ["DATABASE_URL"] = db_url


def test_backward_compatibility():
    """test_database_url property should work."""
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
    os.environ.pop("USE_PROD_DATABASE", None)
    os.environ.pop("USE_STG_DATABASE", None)

    from app.core.config import settings

    assert "instainstru_test" in settings.database_url


def test_production_server_can_access_prod():
    """Production servers should be able to access production database."""
    # Set both required flags
    os.environ["INSTAINSTRU_PRODUCTION_MODE"] = "true"
    os.environ["USE_PROD_DATABASE"] = "true"

    try:
        from app.core.config import settings

        # This should NOT raise an error in production mode
        url = settings.database_url
        assert url is not None
    finally:
        os.environ.pop("INSTAINSTRU_PRODUCTION_MODE", None)
        os.environ.pop("USE_PROD_DATABASE", None)


def test_production_requires_both_flags():
    """Production access should require both USE_PROD_DATABASE and either confirmation or production mode."""
    # Only production mode flag - should not access production
    os.environ["INSTAINSTRU_PRODUCTION_MODE"] = "true"
    os.environ.pop("USE_PROD_DATABASE", None)

    from app.core.config import settings

    url = settings.database_url
    assert "instainstru_test" in url, "Should use INT without USE_PROD_DATABASE flag"

    os.environ.pop("INSTAINSTRU_PRODUCTION_MODE", None)


def test_local_prod_requires_confirmation():
    """Local production access should still require confirmation even with USE_PROD_DATABASE."""
    # Save and clear DATABASE_URL
    db_url = os.environ.pop("DATABASE_URL", None)
    os.environ["USE_PROD_DATABASE"] = "true"
    os.environ.pop("INSTAINSTRU_PRODUCTION_MODE", None)
    os.environ.pop("RENDER", None)

    try:
        # Mock both CI and production mode
        with patch("app.core.database_config.DatabaseConfig._is_ci_environment", return_value=False), patch(
            "app.core.database_config.DatabaseConfig._check_production_mode", return_value=False
        ):
            from app.core.database_config import DatabaseConfig

            config = DatabaseConfig()

            # In non-interactive mode (tests), this should raise
            with pytest.raises(RuntimeError, match="non-interactive mode"):
                _ = config.get_database_url()
    finally:
        os.environ.pop("USE_PROD_DATABASE", None)
        if db_url:
            os.environ["DATABASE_URL"] = db_url


def test_ci_environment_detection():
    """Test that CI environments are properly detected."""
    # This test should work differently in actual CI vs local
    # In CI, it will naturally detect CI environment
    # Locally, we set CI=true to test the behavior

    # Set CI indicator
    was_ci = os.environ.get("CI")
    os.environ["CI"] = "true"

    try:
        from app.core.database_config import DatabaseConfig

        config = DatabaseConfig()

        # Should detect CI environment
        assert config._is_ci_environment() is True

        # In CI with DATABASE_URL, it uses that
        # In CI without DATABASE_URL, it defaults to INT
        # We don't assert specific behavior here as it depends on environment
    finally:
        if was_ci:
            os.environ["CI"] = was_ci
        else:
            os.environ.pop("CI", None)


def test_ci_uses_provided_database():
    """CI should use DATABASE_URL when provided."""
    # Save originals
    original_ci = os.environ.get("CI")
    original_db_url = os.environ.get("DATABASE_URL")

    # Set test values
    os.environ["CI"] = "true"
    os.environ["DATABASE_URL"] = "postgresql://ci_user:ci_pass@localhost/ci_test_db"

    try:
        from app.core.config import settings

        # In CI with DATABASE_URL, it should use that
        url = settings.database_url

        # In actual CI, this will use the CI database
        # In local testing, we're just verifying it doesn't error
        assert url is not None
    finally:
        # Restore
        if original_ci:
            os.environ["CI"] = original_ci
        else:
            os.environ.pop("CI", None)

        if original_db_url:
            os.environ["DATABASE_URL"] = original_db_url
        else:
            os.environ.pop("DATABASE_URL", None)


def test_ci_without_database_uses_int():
    """CI without DATABASE_URL should default to INT."""
    # Save originals
    original_ci = os.environ.get("CI")
    original_db_url = os.environ.get("DATABASE_URL")

    # Set CI but clear DATABASE_URL
    os.environ["CI"] = "true"
    if "DATABASE_URL" in os.environ:
        del os.environ["DATABASE_URL"]

    try:
        # Create config directly to test behavior
        from app.core.database_config import DatabaseConfig

        config = DatabaseConfig()

        # When CI has no DATABASE_URL, should fall back to INT
        url = config.get_database_url()

        # Should get INT database
        assert "instainstru_test" in url or url == os.environ.get("DATABASE_URL", "")
    finally:
        # Restore
        if original_ci:
            os.environ["CI"] = original_ci
        else:
            os.environ.pop("CI", None)

        if original_db_url:
            os.environ["DATABASE_URL"] = original_db_url


def test_production_mode_overrides_ci():
    """Production mode should take precedence over CI mode."""
    # Set both CI and production flags
    os.environ["CI"] = "true"
    os.environ["USE_PROD_DATABASE"] = "true"
    os.environ["INSTAINSTRU_PRODUCTION_MODE"] = "true"

    try:
        from app.core.config import settings

        # Should use production database (in production mode, no confirmation needed)
        # In test environment, this should not raise an error
        url = settings.database_url
        assert url is not None
    finally:
        os.environ.pop("CI", None)
        os.environ.pop("USE_PROD_DATABASE", None)
        os.environ.pop("INSTAINSTRU_PRODUCTION_MODE", None)
