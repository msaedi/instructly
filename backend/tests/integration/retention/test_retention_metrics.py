from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session
from tests._utils.bitmap_avail import seed_day

from app.core.config import settings
from app.monitoring.prometheus_metrics import REGISTRY
from app.services.retention_service import RetentionService


def _configure_retention(monkeypatch: pytest.MonkeyPatch, *, dry_run: bool = False) -> None:
    monkeypatch.setattr(settings, "availability_retention_enabled", True, raising=False)
    monkeypatch.setattr(settings, "availability_retention_days", 180, raising=False)
    monkeypatch.setattr(settings, "availability_retention_keep_recent_days", 30, raising=False)
    monkeypatch.setattr(settings, "availability_retention_dry_run", dry_run, raising=False)


def _counter_value(site_mode: str) -> float:
    labels = {"site_mode": site_mode}
    value = REGISTRY.get_sample_value("availability_days_purged_total", labels)
    return float(value or 0.0)


def _histogram_count() -> float:
    value = REGISTRY.get_sample_value("availability_retention_run_seconds_count")
    return float(value or 0.0)


@pytest.mark.integration
def test_metrics_increment_when_purging(
    monkeypatch: pytest.MonkeyPatch,
    db: Session,
    test_instructor,
) -> None:
    _configure_retention(monkeypatch)

    instructor_id = test_instructor.id
    today = date.today()
    for offset in (190, 200):
        seed_day(db, instructor_id, today - timedelta(days=offset), [("08:00:00", "09:00:00")])

    site_mode = (settings.site_mode or "unknown").strip() or "unknown"
    counter_before = _counter_value(site_mode)
    histogram_before = _histogram_count()

    service = RetentionService(db)
    summary = service.purge_availability_days(today=today)

    counter_after = _counter_value(site_mode)
    histogram_after = _histogram_count()

    assert summary["purged_days"] == 2
    assert counter_after == pytest.approx(counter_before + 2)
    assert histogram_after >= histogram_before + 1
