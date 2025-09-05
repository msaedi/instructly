import re

from fastapi.testclient import TestClient

from app.main import app as asgi_app


def test_rl_metrics_present_in_prometheus_exposition():
    client = TestClient(asgi_app)
    # Hitting a read route in test mode will emit synthetic headers, but we just need /metrics
    resp = client.get("/metrics")
    assert resp.status_code == 200
    text = resp.text

    # Base metrics should exist
    assert "instainstru_rl_decisions_total" in text
    assert "instainstru_rl_retry_after_seconds_bucket" in text

    # PR-8 metrics present
    assert "instainstru_rl_eval_errors_total" in text
    assert "instainstru_rl_eval_duration_seconds_bucket" in text
    assert "instainstru_rl_config_reload_total" in text
    assert "instainstru_rl_active_overrides" in text
