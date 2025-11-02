import pytest


@pytest.fixture(autouse=True)
def _bitmap_env_for_availability_tests(monkeypatch: pytest.MonkeyPatch):
    """Ensure bitmap availability env vars are set for availability integration tests."""
    monkeypatch.setenv("AVAILABILITY_V2_BITMAPS", "1")
    monkeypatch.setenv("AVAILABILITY_ALLOW_PAST", "true")
    monkeypatch.setenv("AVAILABILITY_PERF_DEBUG", "1")
    yield
