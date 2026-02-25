from __future__ import annotations

import importlib
import sys

from app.tasks import celery_init


def _clear_env(monkeypatch) -> None:
    keys = [
        "SITE_MODE",
        "PREVIEW_DATABASE_URL",
        "preview_database_url",
        "PROD_DATABASE_URL",
        "prod_database_url",
        "STG_DATABASE_URL",
        "stg_database_url",
        "RENDER",
        "RENDER_SERVICE_ID",
        "RENDER_SERVICE_NAME",
        "SUPPRESS_DB_MESSAGES",
    ]
    for key in keys:
        monkeypatch.delenv(key, raising=False)


def test_derive_site_mode_explicit(monkeypatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("SITE_MODE", "prod")
    assert celery_init._derive_site_mode() == "prod"


def test_derive_site_mode_preview_db(monkeypatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("PREVIEW_DATABASE_URL", "postgres://example")
    assert celery_init._derive_site_mode() == "preview"


def test_derive_site_mode_prod_db(monkeypatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("PROD_DATABASE_URL", "postgres://example")
    assert celery_init._derive_site_mode() == "prod"


def test_derive_site_mode_stg_db(monkeypatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("STG_DATABASE_URL", "postgres://example")
    assert celery_init._derive_site_mode() == "local"


def test_derive_site_mode_render(monkeypatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("RENDER", "1")
    assert celery_init._derive_site_mode() == "preview"


def test_derive_site_mode_default(monkeypatch) -> None:
    _clear_env(monkeypatch)
    assert celery_init._derive_site_mode() == "int"


def test_module_reload_with_suppress_db_messages(monkeypatch) -> None:
    """L46->exit: SUPPRESS_DB_MESSAGES set → skip print statement."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("SUPPRESS_DB_MESSAGES", "1")
    # Reloading the module exercises the module-level code with the env var set
    importlib.reload(celery_init)
    # If we got here, the print was skipped (no error)
    assert celery_init.site_mode == "int"  # pytest is in sys.modules


def test_module_reload_without_pytest_in_modules(monkeypatch) -> None:
    """L40->44: When pytest is NOT in sys.modules, site_mode is NOT forced to 'int'."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("SUPPRESS_DB_MESSAGES", "1")
    monkeypatch.setenv("SITE_MODE", "preview")

    # Temporarily remove pytest from sys.modules
    pytest_mod = sys.modules.pop("pytest", None)
    try:
        importlib.reload(celery_init)
        # Without pytest override, the derived site_mode should be "preview"
        assert celery_init.site_mode == "preview"
    finally:
        if pytest_mod is not None:
            sys.modules["pytest"] = pytest_mod
        # Re-reload to restore normal state
        importlib.reload(celery_init)


def test_derive_site_mode_preview_db_lowercase(monkeypatch) -> None:
    """Lowercase env var 'preview_database_url' also triggers preview."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("preview_database_url", "postgres://example")
    assert celery_init._derive_site_mode() == "preview"


def test_derive_site_mode_prod_db_lowercase(monkeypatch) -> None:
    """Lowercase env var 'prod_database_url' also triggers prod."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("prod_database_url", "postgres://example")
    assert celery_init._derive_site_mode() == "prod"


def test_derive_site_mode_stg_db_lowercase(monkeypatch) -> None:
    """Lowercase env var 'stg_database_url' also triggers local."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("stg_database_url", "postgres://example")
    assert celery_init._derive_site_mode() == "local"


def test_derive_site_mode_render_service_id(monkeypatch) -> None:
    """RENDER_SERVICE_ID env var triggers preview."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("RENDER_SERVICE_ID", "srv-123")
    assert celery_init._derive_site_mode() == "preview"


def test_derive_site_mode_render_service_name(monkeypatch) -> None:
    """RENDER_SERVICE_NAME env var triggers preview."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("RENDER_SERVICE_NAME", "my-service")
    assert celery_init._derive_site_mode() == "preview"
