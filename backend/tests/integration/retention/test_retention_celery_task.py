from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session
from tests._utils.bitmap_avail import seed_day

from app.core.config import settings
from app.models.availability_day import AvailabilityDay
from app.tasks.celery_app import run_availability_retention


def _configure_retention(
    monkeypatch: pytest.MonkeyPatch,
    *,
    enabled: bool = True,
    ttl: int = 180,
    keep_recent: int = 30,
    dry_run: bool = False,
) -> None:
    monkeypatch.setattr(settings, "availability_retention_enabled", enabled, raising=False)
    monkeypatch.setattr(settings, "availability_retention_days", ttl, raising=False)
    monkeypatch.setattr(settings, "availability_retention_keep_recent_days", keep_recent, raising=False)
    monkeypatch.setattr(settings, "availability_retention_dry_run", dry_run, raising=False)


def _fetch_days(db: Session, instructor_id: str) -> set[date]:
    return {
        row.day_date
        for row in db.query(AvailabilityDay)
        .filter(AvailabilityDay.instructor_id == instructor_id)
        .all()
    }


@pytest.mark.integration
def test_celery_task_runs_retention_policy(
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
    test_instructor,
) -> None:
    _configure_retention(monkeypatch, enabled=True, ttl=180, keep_recent=30, dry_run=False)

    instructor_id = test_instructor.id
    today = date.today()
    stale_day = today - timedelta(days=200)
    future_day = today + timedelta(days=5)

    seed_day(db, instructor_id, stale_day, [("07:00:00", "08:00:00")])
    seed_day(db, instructor_id, future_day, [("09:00:00", "10:00:00")])
    db.commit()

    result = run_availability_retention.apply(args=[], kwargs={}).get()

    assert result["purged_days"] == 1
    remaining = _fetch_days(db, instructor_id)
    assert stale_day not in remaining
    assert future_day in remaining
