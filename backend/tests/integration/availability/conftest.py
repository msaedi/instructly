from fastapi.testclient import TestClient
import pytest

from app.core.config import settings
import app.main
import app.routes.v1.availability_windows as availability_routes
import app.services.availability_service as availability_service_module


@pytest.fixture
def bitmap_env_guardrails(monkeypatch: pytest.MonkeyPatch):
    """
    Apply the production-style guardrail defaults for bitmap availability.
    """
    # Bitmap availability is always enabled; no flag required
    monkeypatch.setenv("AVAILABILITY_ALLOW_PAST", "true")
    monkeypatch.setenv("PAST_EDIT_WINDOW_DAYS", "30")
    monkeypatch.setenv("CLAMP_COPY_TO_FUTURE", "true")
    monkeypatch.setenv("SUPPRESS_PAST_AVAILABILITY_EVENTS", "false")
    monkeypatch.setenv("AVAILABILITY_TEST_MEMORY_CACHE", "1")
    monkeypatch.setenv("AVAILABILITY_PERF_DEBUG", "1")
    monkeypatch.setattr(settings, "past_edit_window_days", 30, raising=False)
    monkeypatch.setattr(settings, "clamp_copy_to_future", True, raising=False)
    monkeypatch.setattr(settings, "suppress_past_availability_events", False, raising=False)
    yield


@pytest.fixture
def bitmap_env_relaxed(monkeypatch: pytest.MonkeyPatch):
    """
    Enable bitmap mode with permissive past edits/copies for focused tests.
    """
    # Always seed bitmaps; no flag required
    monkeypatch.setenv("AVAILABILITY_ALLOW_PAST", "true")
    monkeypatch.setenv("PAST_EDIT_WINDOW_DAYS", "0")
    monkeypatch.setenv("CLAMP_COPY_TO_FUTURE", "false")
    monkeypatch.setenv("SUPPRESS_PAST_AVAILABILITY_EVENTS", "false")
    monkeypatch.setenv("AVAILABILITY_TEST_MEMORY_CACHE", "1")
    monkeypatch.setenv("AVAILABILITY_PERF_DEBUG", "1")
    monkeypatch.setattr(settings, "past_edit_window_days", 0, raising=False)
    monkeypatch.setattr(settings, "clamp_copy_to_future", False, raising=False)
    monkeypatch.setattr(settings, "suppress_past_availability_events", False, raising=False)
    yield


@pytest.fixture
def bitmap_app(monkeypatch: pytest.MonkeyPatch):
    """
    Patch module-level ALLOW_PAST variables without expensive module reloads.

    This fixture is ~10x faster than reloading modules.
    """
    # Set env var for any dynamic reads in functions
    monkeypatch.setenv("AVAILABILITY_ALLOW_PAST", "true")

    # Patch module-level ALLOW_PAST variables directly (no reload needed)
    monkeypatch.setattr(availability_service_module, "ALLOW_PAST", True)
    monkeypatch.setattr(availability_routes, "ALLOW_PAST", True)

    yield app.main


@pytest.fixture
def bitmap_client(bitmap_app) -> TestClient:
    """Return a TestClient backed by the bitmap-enabled app instance."""
    client = TestClient(bitmap_app.fastapi_app, raise_server_exceptions=False)
    try:
        yield client
    finally:
        client.close()


@pytest.fixture
def bitmap_app_allow_past(monkeypatch: pytest.MonkeyPatch):
    """
    Patch for ALLOW_PAST=true without module reloads.
    """
    monkeypatch.setenv("AVAILABILITY_ALLOW_PAST", "true")
    monkeypatch.setattr(availability_service_module, "ALLOW_PAST", True)
    monkeypatch.setattr(availability_routes, "ALLOW_PAST", True)
    yield app.main


@pytest.fixture
def bitmap_app_disallow_past(monkeypatch: pytest.MonkeyPatch):
    """
    Patch for ALLOW_PAST=false without module reloads.
    """
    monkeypatch.setenv("AVAILABILITY_ALLOW_PAST", "false")
    monkeypatch.setattr(availability_service_module, "ALLOW_PAST", False)
    monkeypatch.setattr(availability_routes, "ALLOW_PAST", False)
    yield app.main


@pytest.fixture
def bitmap_client_allow_past(bitmap_app_allow_past) -> TestClient:
    """Return a TestClient with allow_past enabled."""
    client = TestClient(bitmap_app_allow_past.fastapi_app, raise_server_exceptions=False)
    try:
        yield client
    finally:
        client.close()


@pytest.fixture
def bitmap_client_disallow_past(bitmap_app_disallow_past) -> TestClient:
    """Return a TestClient with allow_past disabled."""
    client = TestClient(bitmap_app_disallow_past.fastapi_app, raise_server_exceptions=False)
    try:
        yield client
    finally:
        client.close()


@pytest.fixture
def bitmap_booking_app(monkeypatch: pytest.MonkeyPatch):
    """
    Patch module-level variables for booking tests without module reloads.
    """
    monkeypatch.setenv("AVAILABILITY_ALLOW_PAST", "true")
    monkeypatch.setattr(availability_service_module, "ALLOW_PAST", True)
    monkeypatch.setattr(availability_routes, "ALLOW_PAST", True)
    yield app.main


@pytest.fixture
def bitmap_booking_client(bitmap_booking_app) -> TestClient:
    """Return a TestClient for the bitmap-enabled app instance."""
    client = TestClient(bitmap_booking_app.fastapi_app, raise_server_exceptions=False)
    try:
        yield client
    finally:
        client.close()
