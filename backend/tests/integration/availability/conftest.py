import pytest

from app.core.config import settings


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
