from __future__ import annotations

from datetime import datetime, timezone
import logging
from types import SimpleNamespace
from typing import Any

from fastapi.routing import APIRoute
import pytest

from app.core.config import settings as app_settings
from app.core.constants import ALLOWED_ORIGINS
import app.core.internal_metrics as internal_metrics
import app.core.middleware_setup as middleware_setup
import app.main as main
from app.monitoring.prometheus_metrics import prometheus_metrics
import app.workers.background_jobs as background_jobs


def test_unique_operation_id_formats_route() -> None:
    def handler() -> None:
        return None

    route = APIRoute("/items/{item_id}", handler, methods=["POST", "GET"], name="Fetch Item")
    assert main._unique_operation_id(route) == "get_post__items_item_id__fetch_item"


def test_next_expiry_run_same_day() -> None:
    now = datetime(2024, 1, 1, 2, 0, tzinfo=timezone.utc)
    next_run = background_jobs._next_expiry_run(now)
    assert next_run == datetime(2024, 1, 1, 3, 0, tzinfo=timezone.utc)


def test_next_expiry_run_rolls_forward() -> None:
    now = datetime(2024, 1, 1, 4, 0, tzinfo=timezone.utc)
    next_run = background_jobs._next_expiry_run(now)
    assert next_run == datetime(2024, 1, 2, 3, 0, tzinfo=timezone.utc)


def test_expiry_recheck_url_uses_frontend_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_settings, "frontend_url", "https://example.com/")
    assert (
        background_jobs._expiry_recheck_url()
        == "https://example.com/instructor/onboarding/verification"
    )


def test_expiry_recheck_url_without_frontend_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_settings, "frontend_url", "")
    assert background_jobs._expiry_recheck_url() == "/instructor/onboarding/verification"


def test_compute_allowed_origins_preview_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SITE_MODE", "preview")
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://extra.com, https://extra-two.com")
    monkeypatch.setattr(app_settings, "preview_frontend_domain", "preview.example.com")

    origins = middleware_setup._compute_allowed_origins()
    assert set(origins) == {
        "https://preview.example.com",
        "https://extra.com",
        "https://extra-two.com",
    }


def test_compute_allowed_origins_prod_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SITE_MODE", "prod")
    monkeypatch.setattr(app_settings, "prod_frontend_origins_csv", "")

    origins = middleware_setup._compute_allowed_origins()
    assert origins == ["https://app.instainstru.com"]


def test_compute_allowed_origins_dev_includes_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SITE_MODE", "dev")
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "http://localhost:3000")

    origins = middleware_setup._compute_allowed_origins()
    assert "http://localhost:3000" in origins
    assert set(ALLOWED_ORIGINS).issubset(set(origins))


def test_log_bgc_config_summary_once(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class DummySecret:
        def __init__(self, value: str) -> None:
            self._value = value

        def get_secret_value(self) -> str:
            return self._value

    dummy_settings = SimpleNamespace(
        site_mode="prod",
        checkr_env="sandbox",
        checkr_api_base="https://api.example.com",
        checkr_api_key=DummySecret("secret"),
        checkr_hosted_workflow="workflow",
        checkr_package="basic",
        checkr_default_package="default",
    )
    monkeypatch.setattr(middleware_setup, "settings", dummy_settings)
    monkeypatch.setattr(middleware_setup, "_BGC_ENV_LOGGED", False)

    with caplog.at_level(logging.INFO):
        middleware_setup._log_bgc_config_summary(["https://example.com"])

    assert "BGC config summary" in caplog.text
    assert middleware_setup._BGC_ENV_LOGGED is True


def test_availability_safe_openapi_handles_rebuild_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class DummyModelError:
        @classmethod
        def model_rebuild(cls, **_kwargs: Any) -> None:
            calls.append("error")
            raise RuntimeError("boom")

    class DummyModelOk:
        @classmethod
        def model_rebuild(cls, **_kwargs: Any) -> None:
            calls.append("ok")

    monkeypatch.setattr(main, "WeekSpecificScheduleCreate", DummyModelError)
    monkeypatch.setattr(main, "ValidateWeekRequest", DummyModelOk)
    monkeypatch.setattr(main, "_original_openapi", lambda: {"ok": True})

    assert main._availability_safe_openapi() == {"ok": True}
    assert calls == ["error", "ok"]


def test_prewarm_metrics_cache_handles_error(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, int] = {"prewarm": 0}

    def raise_cache() -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(prometheus_metrics, "prewarm", lambda: calls.update(prewarm=1))
    import app.routes.v1.prometheus as prom

    monkeypatch.setattr(prom, "warm_prometheus_metrics_response_cache", raise_cache)

    internal_metrics.prewarm_metrics_cache()
    assert calls["prewarm"] == 1
