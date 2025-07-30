"""Test that database safety cannot be bypassed."""

import os

import pytest


def test_default_is_int_database():
    """Default database must be INT."""
    # Clear any env vars
    os.environ.pop("USE_PROD_DATABASE", None)
    os.environ.pop("USE_STG_DATABASE", None)

    # Import settings fresh
    from app.core.config import settings

    url = settings.database_url
    assert "instainstru_test" in url, f"Expected INT database, got {url}"


def test_cannot_access_prod_without_confirmation():
    """Production database requires confirmation in non-interactive mode."""
    os.environ["USE_PROD_DATABASE"] = "true"
    # Ensure we're not in CI environment for this test
    ci_env = os.environ.pop("CI", None)
    github_env = os.environ.pop("GITHUB_ACTIONS", None)

    try:
        # Create fresh DatabaseConfig to test
        from app.core.database_config import DatabaseConfig

        config = DatabaseConfig()

        # In non-interactive mode (like tests), this should raise RuntimeError
        with pytest.raises(RuntimeError, match="Production database access requested in non-interactive mode"):
            _ = config.get_database_url()
    finally:
        # Cleanup
        os.environ.pop("USE_PROD_DATABASE", None)
        if ci_env:
            os.environ["CI"] = ci_env
        if github_env:
            os.environ["GITHUB_ACTIONS"] = github_env


def test_old_scripts_safe_by_default():
    """Old patterns must be safe."""
    # Clear any env vars
    os.environ.pop("USE_PROD_DATABASE", None)
    os.environ.pop("USE_STG_DATABASE", None)

    from app.core.config import settings

    # Even direct access should be safe
    url = settings.database_url
    assert "instainstru_test" in url, f"Old patterns should default to INT, got {url}"


def test_stg_database_with_flag():
    """Staging database accessible with flag."""
    os.environ["USE_STG_DATABASE"] = "true"
    # Ensure we're not in CI environment for this test
    ci_env = os.environ.pop("CI", None)
    github_env = os.environ.pop("GITHUB_ACTIONS", None)
    db_url = os.environ.pop("DATABASE_URL", None)

    try:
        # Create fresh DatabaseConfig to test
        from app.core.database_config import DatabaseConfig

        config = DatabaseConfig()

        url = config.get_database_url()
        assert "instainstru_stg" in url, f"Expected STG database, got {url}"
    finally:
        # Cleanup
        os.environ.pop("USE_STG_DATABASE", None)
        if ci_env:
            os.environ["CI"] = ci_env
        if github_env:
            os.environ["GITHUB_ACTIONS"] = github_env
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
    # Clear any env vars
    os.environ.pop("USE_PROD_DATABASE", None)
    os.environ.pop("USE_STG_DATABASE", None)

    # We can't actually run alembic in tests, but we can check
    # that settings.database_url returns INT
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
        # In test environment, we won't actually get prod URL
        # but we should not get an error
        assert url is not None
    finally:
        # Cleanup
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

    # Cleanup
    os.environ.pop("INSTAINSTRU_PRODUCTION_MODE", None)


def test_local_prod_requires_confirmation():
    """Local production access should still require confirmation even with USE_PROD_DATABASE."""
    # Set production flag but not production mode
    os.environ["USE_PROD_DATABASE"] = "true"
    os.environ.pop("INSTAINSTRU_PRODUCTION_MODE", None)
    os.environ.pop("RENDER", None)
    # Ensure we're not in CI environment for this test
    ci_env = os.environ.pop("CI", None)
    github_env = os.environ.pop("GITHUB_ACTIONS", None)

    try:
        # Create fresh DatabaseConfig to test
        from app.core.database_config import DatabaseConfig

        config = DatabaseConfig()

        # In non-interactive mode (tests), this should raise
        with pytest.raises(RuntimeError, match="non-interactive mode"):
            _ = config.get_database_url()
    finally:
        # Cleanup
        os.environ.pop("USE_PROD_DATABASE", None)
        if ci_env:
            os.environ["CI"] = ci_env
        if github_env:
            os.environ["GITHUB_ACTIONS"] = github_env


def test_ci_environment_detection():
    """Test that CI environments are properly detected."""
    # Set CI indicator
    os.environ["CI"] = "true"

    try:
        from app.core.database_config import DatabaseConfig

        config = DatabaseConfig()
        # Should detect CI environment
        assert config._is_ci_environment() is True

        # CI should default to INT database if no DATABASE_URL
        os.environ.pop("DATABASE_URL", None)
        url = config.get_database_url()
        assert "instainstru_test" in url
    finally:
        # Cleanup
        os.environ.pop("CI", None)


def test_ci_uses_provided_database():
    """CI should use DATABASE_URL when provided."""
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
        os.environ.pop("DATABASE_URL", None)


def test_ci_without_database_uses_int():
    """CI without DATABASE_URL should default to INT."""
    # Set CI but no DATABASE_URL
    os.environ["CI"] = "true"
    os.environ.pop("DATABASE_URL", None)

    try:
        from app.core.config import settings

        # Should default to INT database
        url = settings.database_url
        assert "instainstru_test" in url
    finally:
        # Cleanup
        os.environ.pop("CI", None)


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
        # Cleanup
        os.environ.pop("CI", None)
        os.environ.pop("USE_PROD_DATABASE", None)
        os.environ.pop("INSTAINSTRU_PRODUCTION_MODE", None)
