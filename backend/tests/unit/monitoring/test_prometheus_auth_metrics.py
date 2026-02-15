from __future__ import annotations

from app.monitoring.prometheus_metrics import REGISTRY, prometheus_metrics


def _sample(metric_name: str, labels: dict[str, str]) -> float:
    value = REGISTRY.get_sample_value(metric_name, labels)
    return float(value or 0.0)


def test_record_token_revocation_increments_allowed_trigger() -> None:
    labels = {"trigger": "logout"}
    before = _sample("instainstru_auth_token_revocation_total", labels)
    prometheus_metrics.record_token_revocation("logout")
    after = _sample("instainstru_auth_token_revocation_total", labels)
    assert after >= before + 1.0


def test_record_token_revocation_increments_deactivation_trigger() -> None:
    labels = {"trigger": "deactivation"}
    before = _sample("instainstru_auth_token_revocation_total", labels)
    prometheus_metrics.record_token_revocation("deactivation")
    after = _sample("instainstru_auth_token_revocation_total", labels)
    assert after >= before + 1.0


def test_record_token_revocation_maps_unknown_trigger() -> None:
    labels = {"trigger": "unknown"}
    before = _sample("instainstru_auth_token_revocation_total", labels)
    prometheus_metrics.record_token_revocation("not_allowed")
    after = _sample("instainstru_auth_token_revocation_total", labels)
    assert after >= before + 1.0


def test_record_token_rejection_increments_allowed_reason() -> None:
    labels = {"reason": "revoked"}
    before = _sample("instainstru_auth_token_rejection_total", labels)
    prometheus_metrics.record_token_rejection("revoked")
    after = _sample("instainstru_auth_token_rejection_total", labels)
    assert after >= before + 1.0


def test_record_token_rejection_maps_unknown_reason() -> None:
    labels = {"reason": "unknown"}
    before = _sample("instainstru_auth_token_rejection_total", labels)
    prometheus_metrics.record_token_rejection("other")
    after = _sample("instainstru_auth_token_rejection_total", labels)
    assert after >= before + 1.0
