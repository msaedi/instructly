from __future__ import annotations

import asyncio
import base64
from concurrent.futures import CancelledError as FuturesCancelledError
import contextlib
import importlib
import os
from typing import Generator

import pytest


def _gen_key() -> str:
    """Generate a urlsafe base64-encoded 32-byte key suitable for tests."""

    return base64.urlsafe_b64encode(os.urandom(32)).decode("utf-8")


@contextlib.contextmanager
def _app_with_env(site_mode: str | None, key: str | None) -> Generator[None, None, None]:
    """Reload configuration and application using the provided environment."""

    from importlib import reload

    prev_site_mode = os.environ.get("SITE_MODE")
    prev_key = os.environ.get("BGC_ENCRYPTION_KEY")
    prev_checkr_env = os.environ.get("CHECKR_ENV")
    prev_is_testing = os.environ.get("is_testing")

    cfg_module = None
    app_module = None

    try:
        if site_mode is not None:
            os.environ["SITE_MODE"] = site_mode
        else:
            os.environ.pop("SITE_MODE", None)

        if site_mode == "prod":
            os.environ["CHECKR_ENV"] = "production"
            os.environ["is_testing"] = "false"
        else:
            os.environ["CHECKR_ENV"] = "sandbox"
            if prev_is_testing is not None:
                os.environ["is_testing"] = prev_is_testing
            else:
                os.environ.pop("is_testing", None)

        if key is not None:
            os.environ["BGC_ENCRYPTION_KEY"] = key
        else:
            os.environ["BGC_ENCRYPTION_KEY"] = ""

        import app.core.config as cfg

        cfg_module = reload(cfg)
        app_module = reload(importlib.import_module("app.main"))

        try:
            from fastapi.testclient import TestClient
        except ImportError:  # pragma: no cover - optional dependency guard
            TestClient = None  # type: ignore[assignment]

        if TestClient is None:
            app_module._validate_startup_config()
            yield
        else:
            try:
                with TestClient(app_module.fastapi_app):
                    yield
            except (asyncio.CancelledError, FuturesCancelledError):
                pass
    finally:
        if prev_site_mode is not None:
            os.environ["SITE_MODE"] = prev_site_mode
        else:
            os.environ.pop("SITE_MODE", None)

        if prev_checkr_env is not None:
            os.environ["CHECKR_ENV"] = prev_checkr_env
        else:
            os.environ.pop("CHECKR_ENV", None)

        if prev_key is not None:
            os.environ["BGC_ENCRYPTION_KEY"] = prev_key
        else:
            os.environ.pop("BGC_ENCRYPTION_KEY", None)

        if prev_is_testing is not None:
            os.environ["is_testing"] = prev_is_testing
        else:
            os.environ.pop("is_testing", None)

        if cfg_module is not None:
            with contextlib.suppress(Exception):
                reload(cfg_module)
        if app_module is not None:
            with contextlib.suppress(Exception):
                reload(app_module)


def test_nonprod_startup_without_key_does_not_raise() -> None:
    with _app_with_env(site_mode="dev", key=None):
        pass


def test_prod_startup_without_key_raises() -> None:
    with pytest.raises(RuntimeError, match="BGC_ENCRYPTION_KEY must be configured"):
        with _app_with_env(site_mode="prod", key=None):
            pass


def test_prod_startup_with_valid_key_succeeds() -> None:
    with _app_with_env(site_mode="prod", key=_gen_key()):
        pass
