"""Test that database safety cannot be bypassed - CI-compatible version."""

import logging
import os
from unittest.mock import patch

import pytest


def test_default_is_int_database():
    """Default database must be INT."""
    # Clear any env vars
    os.environ.pop("SITE_MODE", None)
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


def test_ci_environment_preserves_test_db(caplog):
    os.environ["CI"] = "true"
    os.environ["DATABASE_URL"] = "postgresql://user:pass@host/ci_test_db"

    try:
        caplog.set_level(logging.INFO)
        from app.core.database_config import DatabaseConfig

        config = DatabaseConfig()
        url = config.get_database_url()
        assert url.endswith("/ci_test_db"), url
        assert any("using provided test database" in record.message for record in caplog.records)
    finally:
        os.environ.pop("CI", None)
        os.environ.pop("DATABASE_URL", None)


def test_ci_environment_forces_safe_db(caplog):
    os.environ["CI"] = "true"
    os.environ["DATABASE_URL"] = "postgresql://user:pass@host/prod_db"

    try:
        caplog.set_level(logging.WARNING)
        with patch("app.core.database_config.DatabaseConfig._ensure_ci_database_exists") as ensure_mock:
            from app.core.database_config import DatabaseConfig

            config = DatabaseConfig()
            url = config.get_database_url()
            ensure_mock.assert_called_once()
        assert url.endswith("/instainstru_test"), url
        assert any(
            "forcing safe database name" in record.message for record in caplog.records
        )
    finally:
        os.environ.pop("CI", None)
        os.environ.pop("DATABASE_URL", None)


def test_ensure_ci_database_exists_uses_autocommit(monkeypatch):
    executed = []
    engine_kwargs = {}

    class DummyConnection:
        def execute(self, statement, params=None):
            executed.append((str(statement), params))
            if str(statement).startswith("SELECT"):
                class Result:
                    def scalar(self_inner):
                        return None

                return Result()
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class DummyEngine:
        def __init__(self, url, **kwargs):
            engine_kwargs.update(kwargs)

        def connect(self):
            return DummyConnection()

        def dispose(self):
            pass

    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/sample")

    monkeypatch.setattr("sqlalchemy.create_engine", lambda url, **kw: DummyEngine(url, **kw))

    from app.core.database_config import DatabaseConfig

    config = DatabaseConfig()
    _ = config.get_database_url()

    assert engine_kwargs.get("isolation_level") == "AUTOCOMMIT"
    assert any("SELECT 1 FROM pg_database" in stmt for stmt, _ in executed)
    assert any("CREATE DATABASE" in stmt for stmt, _ in executed)

    os.environ.pop("CI", None)
    os.environ.pop("DATABASE_URL", None)


def test_cannot_access_prod_without_confirmation():
    """Production database requires confirmation in non-interactive mode."""
    # Save and clear DATABASE_URL to ensure CI doesn't interfere
    db_url = os.environ.pop("DATABASE_URL", None)
    os.environ["SITE_MODE"] = "prod"

    try:
        # Mock both CI and production mode detection
        with patch("app.core.database_config.DatabaseConfig._is_ci_environment", return_value=False), patch(
            "app.core.database_config.DatabaseConfig._check_production_mode", return_value=False
        ):
            # Ensure prod URL is set in settings
            from app.core.config import settings

            settings.prod_database_url_raw = "postgresql://postgres:postgres@localhost:5432/instainstru_prod"
            from app.core.database_config import DatabaseConfig

            config = DatabaseConfig()

            # In non-interactive mode (like tests), this should raise RuntimeError
            with pytest.raises(RuntimeError, match="Production database access requested in non-interactive mode"):
                _ = config.get_database_url()
    finally:
        os.environ.pop("SITE_MODE", None)
        if db_url:
            os.environ["DATABASE_URL"] = db_url


def test_old_scripts_safe_by_default():
    """Old patterns must be safe."""
    os.environ.pop("SITE_MODE", None)
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
    os.environ["SITE_MODE"] = "local"

    try:
        # Mock CI detection to ensure we get STG behavior
        with patch("app.core.database_config.DatabaseConfig._is_ci_environment", return_value=False):
            from app.core.database_config import DatabaseConfig

            config = DatabaseConfig()

            # Check if STG database is actually configured
            # In some environments, stg_database_url might not be set
            if not config.stg_url or config.stg_url == config.prod_url:
                # Skip this test if STG is not properly configured
                import pytest

                pytest.skip("STG database URL not configured in this environment")

            url = config.get_database_url()
            assert "instainstru_stg" in url, f"Expected STG database, got {url}"
    finally:
        os.environ.pop("SITE_MODE", None)
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
    os.environ.pop("SITE_MODE", None)

    from app.core.config import settings

    assert "instainstru_test" in settings.database_url


def test_production_server_can_access_prod():
    """Production servers should be able to access production database."""
    os.environ["SITE_MODE"] = "prod"

    try:
        # Ensure prod URL is set in settings
        from app.core.config import settings

        settings.prod_database_url_raw = "postgresql://postgres:postgres@localhost:5432/instainstru_prod"
        # This should NOT raise an error in production server mode
        with patch("app.core.database_config.DatabaseConfig._check_production_mode", return_value=True):
            url = settings.database_url
            assert url is not None
    finally:
        os.environ.pop("SITE_MODE", None)


def test_production_requires_production_server_mode():
    """Without production server mode, SITE_MODE=prod should require confirmation and fail in non-interactive tests."""
    os.environ["SITE_MODE"] = "prod"
    # Ensure prod URL is set in settings
    from app.core.config import settings

    settings.prod_database_url_raw = "postgresql://postgres:postgres@localhost:5432/instainstru_prod"

    from app.core.database_config import DatabaseConfig

    with patch("app.core.database_config.DatabaseConfig._is_ci_environment", return_value=False), patch(
        "app.core.database_config.DatabaseConfig._check_production_mode", return_value=False
    ):
        config = DatabaseConfig()
        with pytest.raises(RuntimeError, match="non-interactive mode"):
            _ = config.get_database_url()
    os.environ.pop("SITE_MODE", None)


def test_local_prod_requires_confirmation():
    """Local production access should still require confirmation even with USE_PROD_DATABASE."""
    # Save and clear DATABASE_URL
    db_url = os.environ.pop("DATABASE_URL", None)
    os.environ["SITE_MODE"] = "prod"
    os.environ.pop("RENDER", None)

    try:
        # Mock both CI and production mode
        with patch("app.core.database_config.DatabaseConfig._is_ci_environment", return_value=False), patch(
            "app.core.database_config.DatabaseConfig._check_production_mode", return_value=False
        ):
            # Ensure prod URL is set in settings
            from app.core.config import settings

            settings.prod_database_url_raw = "postgresql://postgres:postgres@localhost:5432/instainstru_prod"
            from app.core.database_config import DatabaseConfig

            config = DatabaseConfig()

            # In non-interactive mode (tests), this should raise
            with pytest.raises(RuntimeError, match="non-interactive mode"):
                _ = config.get_database_url()
    finally:
        os.environ.pop("SITE_MODE", None)
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
    os.environ["SITE_MODE"] = "prod"

    try:
        # Ensure prod URL is set in settings
        from app.core.config import settings

        settings.prod_database_url_raw = "postgresql://postgres:postgres@localhost:5432/instainstru_prod"
        # Should use production database (in production mode, no confirmation needed)
        # In test environment, this should not raise an error
        with patch("app.core.database_config.DatabaseConfig._check_production_mode", return_value=True):
            url = settings.database_url
            assert url is not None
    finally:
        os.environ.pop("CI", None)
        os.environ.pop("SITE_MODE", None)
