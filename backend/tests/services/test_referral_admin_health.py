from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.services.referral_service as referral_service_module
from app.services.referral_service import ReferralService


@pytest.fixture
def referral_service(db):
    return ReferralService(db)


def test_get_admin_health_reports_live_workers(referral_service, monkeypatch):
    monkeypatch.setattr(
        referral_service.referral_reward_repo,
        "counts_by_status",
        lambda: {
            "pending": 5,
            "unlocked": 3,
            "redeemed": 4,
            "void": 1,
        },
    )
    monkeypatch.setattr(
        referral_service.referral_reward_repo,
        "count_pending_due",
        lambda now: 2,
    )

    class HealthyControl:
        def ping(self, timeout: int = 1):
            return [{"celery@worker-1": {"ok": "pong"}}]

    monkeypatch.setattr(
        referral_service_module,
        "celery_app",
        SimpleNamespace(control=HealthyControl()),
    )

    health = referral_service.get_admin_health()

    assert health.workers_alive == 1
    assert health.workers == ["celery@worker-1"]
    assert health.backlog_pending_due == 2
    assert health.pending_total == 5
    assert health.unlocked_total == 3
    assert health.void_total == 1


def test_get_admin_health_handles_ping_failures(referral_service, monkeypatch):
    monkeypatch.setattr(
        referral_service.referral_reward_repo,
        "counts_by_status",
        lambda: {
            "pending": 0,
            "unlocked": 0,
            "redeemed": 0,
            "void": 0,
        },
    )
    monkeypatch.setattr(
        referral_service.referral_reward_repo,
        "count_pending_due",
        lambda now: 0,
    )

    class FailingControl:
        def ping(self, timeout: int = 1):  # pragma: no cover - intentionally raising
            raise TimeoutError("ping timeout")

    monkeypatch.setattr(
        referral_service_module,
        "celery_app",
        SimpleNamespace(control=FailingControl()),
    )

    health = referral_service.get_admin_health()

    assert health.workers_alive == 0
    assert health.workers == []
    assert health.backlog_pending_due == 0
