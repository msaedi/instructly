from __future__ import annotations

import base64
import os

import pytest


def _gen_key() -> str:
    """Generate a urlsafe base64-encoded 32-byte key suitable for tests."""
    return base64.urlsafe_b64encode(os.urandom(32)).decode("utf-8")


def test_nonprod_startup_without_key_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-prod mode doesn't require encryption key."""
    # Set environment so settings.site_mode property returns "dev"
    monkeypatch.setenv("SITE_MODE", "dev")

    from app.main import _validate_startup_config

    # For non-prod, no key is needed - should not raise
    _validate_startup_config()


def test_prod_startup_without_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prod mode without key raises RuntimeError."""
    # Set environment for prod mode
    monkeypatch.setenv("SITE_MODE", "prod")

    # Mock the getattr to return None for bgc_encryption_key
    # The validation function uses getattr(runtime_settings, "bgc_encryption_key", None)
    original_getattr = getattr

    def mock_getattr(obj, name, *default):
        if name == "bgc_encryption_key":
            return None
        return original_getattr(obj, name, *default)

    monkeypatch.setattr("builtins.getattr", mock_getattr)

    from app.main import _validate_startup_config

    with pytest.raises(RuntimeError, match="BGC_ENCRYPTION_KEY must be configured"):
        _validate_startup_config()


def test_prod_startup_with_valid_key_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prod mode with valid key succeeds."""
    valid_key = _gen_key()

    # Set environment for prod mode
    monkeypatch.setenv("SITE_MODE", "prod")

    # Mock the getattr to return the valid key
    original_getattr = getattr

    def mock_getattr(obj, name, *default):
        if name == "bgc_encryption_key":
            return valid_key
        return original_getattr(obj, name, *default)

    monkeypatch.setattr("builtins.getattr", mock_getattr)

    from app.main import _validate_startup_config

    # Should not raise
    _validate_startup_config()
