from __future__ import annotations

import importlib
from unittest.mock import patch

from pydantic import SecretStr
import pytest

from app.core import config as config_module
from app.core.config import Settings, assert_env, resolve_referrals_step, settings


def test_classify_site_mode_variants():
    normalized, is_prod, is_non_prod = config_module._classify_site_mode("PROD")
    assert normalized == "prod"
    assert is_prod is True
    assert is_non_prod is False

    normalized, is_prod, is_non_prod = config_module._classify_site_mode("local")
    assert normalized == "local"
    assert is_prod is False
    assert is_non_prod is True

    normalized, is_prod, is_non_prod = config_module._classify_site_mode(None)
    assert normalized == ""
    assert is_prod is False
    assert is_non_prod is False


def test_default_session_cookie_name():
    assert config_module._default_session_cookie_name() == "sid"


def test_resolve_referrals_step_defaults():
    env = {"SITE_MODE": ""}
    assert resolve_referrals_step(raw_value="3", env=env) == 3
    assert resolve_referrals_step(raw_value="abc", env=env) == 0
    assert resolve_referrals_step(site_mode="local", env=env) == 4
    assert resolve_referrals_step(site_mode="prod", env=env) == 0


def test_env_bool_parsing(monkeypatch):
    cfg = Settings()

    monkeypatch.setenv("FLAG", "true")
    assert cfg.env_bool("FLAG") is True

    monkeypatch.setenv("FLAG", "0")
    assert cfg.env_bool("FLAG") is False

    monkeypatch.delenv("FLAG", raising=False)
    assert cfg.env_bool("FLAG", default=True) is True


def test_parse_metrics_ip_allowlist():
    assert Settings._parse_metrics_ip_allowlist(None) == []
    assert Settings._parse_metrics_ip_allowlist("1.1.1.1, 2.2.2.2") == [
        "1.1.1.1",
        "2.2.2.2",
    ]
    assert Settings._parse_metrics_ip_allowlist(["3.3.3.3", ""]) == ["3.3.3.3"]
    with pytest.raises(ValueError):
        Settings._parse_metrics_ip_allowlist(123)


def test_cookie_validators():
    assert Settings._coerce_cookie_secure("TRUE") is True
    assert Settings._normalize_samesite(None) == "lax"
    assert Settings._normalize_samesite("Strict") == "strict"
    with pytest.raises(ValueError):
        Settings._normalize_samesite("bad")


def test_cookie_policy_hosted(monkeypatch):
    monkeypatch.setenv("SITE_MODE", "preview")
    cfg = Settings()
    assert cfg.session_cookie_secure is True
    assert cfg.session_cookie_domain == ".instainstru.com"


def test_webhook_secrets_property():
    cfg = Settings()
    cfg.stripe_webhook_secret = SecretStr("whsec_1")
    cfg.stripe_webhook_secret_platform = SecretStr("whsec_2")
    cfg.stripe_webhook_secret_connect = "whsec_3"

    assert cfg.webhook_secrets == ["whsec_1", "whsec_2", "whsec_3"]


def test_validate_test_database_indicator():
    info = type("Info", (), {"data": {"production_database_indicators": ["prod"]}})()
    with pytest.raises(ValueError):
        Settings.validate_test_database("postgres://prod-db", info)


def test_is_production_database():
    cfg = Settings.model_validate(
        {
            "production_database_indicators": ["prod"],
            "prod_database_url": "postgres://prod-db",
        }
    )
    assert cfg.is_production_database() is True
    assert cfg.is_production_database("postgres://test-db") is False


def test_database_url_resolution(monkeypatch):
    with patch("app.core.database_config.DatabaseConfig.get_database_url", return_value="db-url"):
        cfg = Settings()
        assert cfg.database_url == "db-url"
        assert cfg.get_database_url() == "db-url"


def test_settings_repr_and_str_mask_secret_values():
    masked_values = {
        "RESEND_API_KEY": "re_super_secret_value",
        "REDIS_URL": "redis://:ultra-secret@localhost:6379/0",
        "VAPID_PRIVATE_KEY": "private-vapid-secret",
        "ADMIN_PASSWORD": "admin-super-secret",
    }
    cfg = Settings.model_validate(masked_values)
    rendered = f"{cfg!r}\n{cfg}"

    for raw_value in masked_values.values():
        assert raw_value not in rendered


def test_test_and_stg_database_url_accessors():
    cfg = Settings.model_validate(
        {
            "test_database_url": "postgres://test-db",
            "stg_database_url": "postgres://stg-db",
        }
    )
    assert cfg.test_database_url == "postgres://test-db"
    assert cfg.stg_database_url == "postgres://stg-db"


def test_assert_env_guardrails(monkeypatch):
    monkeypatch.setattr(settings, "checkr_fake", False, raising=False)
    monkeypatch.setattr(settings, "allow_sandbox_checkr_in_prod", False, raising=False)

    assert_env("prod", "production", fake=False, allow_override=False)
    with pytest.raises(RuntimeError):
        assert_env("prod", "sandbox", fake=False, allow_override=False)

    assert_env("stg", "sandbox", fake=False, allow_override=False)
    with pytest.raises(RuntimeError):
        assert_env("stg", "production", fake=False, allow_override=False)


def test_reload_config_module(monkeypatch):
    monkeypatch.setenv("SITE_MODE", "local")
    reloaded = importlib.reload(config_module)
    assert reloaded.settings.site_mode == "local"


class TestFlowerConfigProperties:
    """Tests for Flower configuration properties."""

    def test_flower_user_with_basic_auth(self):
        """Test flower_user extracts username from FLOWER_BASIC_AUTH."""
        cfg = Settings()
        cfg.flower_basic_auth = "admin:secret123"
        assert cfg.flower_user == "admin"

    def test_flower_password_with_basic_auth(self):
        """Test flower_password extracts password from FLOWER_BASIC_AUTH."""
        cfg = Settings()
        cfg.flower_basic_auth = "admin:secret123"
        assert cfg.flower_password == "secret123"

    def test_flower_password_with_colon_in_password(self):
        """Test flower_password handles passwords containing colons."""
        cfg = Settings()
        cfg.flower_basic_auth = "admin:secret:with:colons"
        assert cfg.flower_user == "admin"
        assert cfg.flower_password == "secret:with:colons"

    def test_flower_user_no_basic_auth(self):
        """Test flower_user returns None when FLOWER_BASIC_AUTH not set."""
        cfg = Settings()
        cfg.flower_basic_auth = None
        assert cfg.flower_user is None

    def test_flower_password_no_basic_auth(self):
        """Test flower_password returns None when FLOWER_BASIC_AUTH not set."""
        cfg = Settings()
        cfg.flower_basic_auth = None
        assert cfg.flower_password is None

    def test_flower_user_no_colon(self):
        """Test flower_user returns None when FLOWER_BASIC_AUTH has no colon."""
        cfg = Settings()
        cfg.flower_basic_auth = "invalid-no-colon"
        assert cfg.flower_user is None

    def test_flower_password_no_colon(self):
        """Test flower_password returns None when FLOWER_BASIC_AUTH has no colon."""
        cfg = Settings()
        cfg.flower_basic_auth = "invalid-no-colon"
        assert cfg.flower_password is None

    def test_flower_url_default(self):
        """Test flower_url has correct default value."""
        cfg = Settings()
        assert cfg.flower_url == "http://localhost:5555"
