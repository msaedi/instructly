from __future__ import annotations

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
