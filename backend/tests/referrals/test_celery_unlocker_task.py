from __future__ import annotations

from unittest.mock import patch

from app.tasks.celery_app import celery_app
from app.tasks.referrals import run_unlocker


def test_run_unlocker_task_invokes_unlocker_main() -> None:
    payload = {"processed": 5, "unlocked": 3, "voided": 1, "expired": 1}
    with patch("app.tasks.referrals.unlocker_main", return_value=payload) as mock_main:
        result = run_unlocker.run(limit=123, dry_run=True)

    assert result == payload
    mock_main.assert_called_once_with(limit=123, dry_run=True)


def test_referral_unlocker_schedule_registered() -> None:
    schedule = celery_app.conf.beat_schedule
    assert "referrals-unlock-every-15m" in schedule
    assert (
        schedule["referrals-unlock-every-15m"]["task"]
        == "app.tasks.referrals.run_unlocker"
    )
