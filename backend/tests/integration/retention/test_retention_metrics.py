
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.auth import create_access_token
from app.core.enums import RoleName
from app.models.availability import AvailabilitySlot
from app.services.permission_service import PermissionService
from app.tasks.retention_tasks import purge_soft_deleted_task


@pytest.mark.integration
def test_retention_metrics_lite(monkeypatch, client, db: Session, test_instructor, sample_admin_for_privacy) -> None:
    monkeypatch.setenv("AVAILABILITY_PERF_DEBUG", "1")
    monkeypatch.setenv("AVAILABILITY_TEST_MEMORY_CACHE", "1")

    old_timestamp = datetime.now(timezone.utc) - timedelta(days=40)

    slot = AvailabilitySlot(
        instructor_id=test_instructor.id,
        specific_date=date.today(),
        start_time=time(hour=7, minute=0),
        end_time=time(hour=8, minute=0),
        deleted_at=old_timestamp,
    )
    db.add(slot)
    db.commit()

    permission_service = PermissionService(db)
    permission_service.assign_role(sample_admin_for_privacy.id, RoleName.ADMIN)
    db.commit()

    token = create_access_token(data={"sub": sample_admin_for_privacy.email})
    headers = {"Authorization": f"Bearer {token}"}

    purge_soft_deleted_task.apply(
        args=[],
        kwargs={"days": 30, "chunk_size": 10, "dry_run": False},
    ).get()

    response = client.get("/ops/metrics-lite", headers=headers)
    assert response.status_code == 200

    body = response.text
    assert "retention_purge_total" in body
    assert "availability_slots" in body
    assert "retention_purge_chunk_seconds" in body
