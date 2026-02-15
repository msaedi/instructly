from importlib import reload


def _fresh_settings():
    from app.core import config as cfg

    reload(cfg)
    return cfg.Settings()


def test_env_mapping(monkeypatch, isolate_settings_env):
    monkeypatch.setenv("SITE_MODE", "local")
    monkeypatch.setenv("SESSION_COOKIE_NAME", "sid")
    monkeypatch.setenv("SESSION_COOKIE_SAMESITE", "lax")
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("EMAIL_PROVIDER", "console")
    monkeypatch.setenv("TOTP_VALID_WINDOW", "1")

    settings = _fresh_settings()
    assert settings.session_cookie_name == "sid"
    assert settings.session_cookie_samesite == "lax"
    assert settings.session_cookie_secure is False
    assert settings.email_provider == "console"
    assert settings.totp_valid_window == 1
