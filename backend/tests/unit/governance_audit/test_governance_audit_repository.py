from datetime import datetime, timedelta, timezone

import pytest

from app.models.audit_log import AuditLogEntry
from app.repositories.governance_audit_repository import GovernanceAuditRepository


@pytest.fixture
def repository(db):
    return GovernanceAuditRepository(db)


def _create_entry(
    repo: GovernanceAuditRepository,
    *,
    timestamp: datetime,
    actor_type: str,
    actor_id: str | None,
    actor_email: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None,
    status: str,
) -> AuditLogEntry:
    entry = AuditLogEntry(
        timestamp=timestamp,
        actor_type=actor_type,
        actor_id=actor_id,
        actor_email=actor_email,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        status=status,
        created_at=timestamp,
    )
    repo.write(entry)
    return entry


def test_search_filters_and_summary(repository: GovernanceAuditRepository) -> None:
    now = datetime.now(timezone.utc)
    _create_entry(
        repository,
        timestamp=now - timedelta(hours=2),
        actor_type="user",
        actor_id="user-1",
        actor_email="user1@example.com",
        action="booking.cancel",
        resource_type="booking",
        resource_id="booking-1",
        status="success",
    )
    recent_user = _create_entry(
        repository,
        timestamp=now - timedelta(minutes=30),
        actor_type="user",
        actor_id="user-2",
        actor_email="user2@example.com",
        action="user.update",
        resource_type="user",
        resource_id="user-2",
        status="failed",
    )
    recent_system = _create_entry(
        repository,
        timestamp=now - timedelta(minutes=5),
        actor_type="system",
        actor_id="system",
        actor_email=None,
        action="payment.capture",
        resource_type="payment",
        resource_id="booking-1",
        status="success",
    )

    entries, total, summary = repository.search(since_hours=1, limit=10)
    assert total == 2
    assert [entry.id for entry in entries] == [recent_system.id, recent_user.id]
    assert summary["by_action"]["payment.capture"] == 1
    assert summary["by_action"]["user.update"] == 1
    assert summary["by_actor_type"]["system"] == 1
    assert summary["by_actor_type"]["user"] == 1

    entries, total, summary = repository.search(
        actor_email="user2@example.com",
        status="failed",
        since_hours=24,
        limit=5,
    )
    assert total == 1
    assert entries[0].id == recent_user.id
    assert summary["by_status"]["failed"] == 1


def test_list_by_resource(repository: GovernanceAuditRepository) -> None:
    now = datetime.now(timezone.utc)
    first = _create_entry(
        repository,
        timestamp=now - timedelta(minutes=10),
        actor_type="user",
        actor_id="user-1",
        actor_email="user1@example.com",
        action="booking.create",
        resource_type="booking",
        resource_id="booking-1",
        status="success",
    )
    second = _create_entry(
        repository,
        timestamp=now - timedelta(minutes=1),
        actor_type="system",
        actor_id="system",
        actor_email=None,
        action="booking.complete",
        resource_type="booking",
        resource_id="booking-1",
        status="success",
    )

    entries = repository.list_by_resource(resource_type="booking", resource_id="booking-1", limit=10)
    assert [entry.id for entry in entries] == [second.id, first.id]


def test_search_filters_by_actor_and_resource(repository: GovernanceAuditRepository) -> None:
    now = datetime.now(timezone.utc)
    _create_entry(
        repository,
        timestamp=now - timedelta(minutes=20),
        actor_type="user",
        actor_id="user-1",
        actor_email="user1@example.com",
        action="booking.create",
        resource_type="booking",
        resource_id="booking-1",
        status="success",
    )
    target = _create_entry(
        repository,
        timestamp=now - timedelta(minutes=5),
        actor_type="system",
        actor_id="system",
        actor_email=None,
        action="payment.capture",
        resource_type="payment",
        resource_id="booking-1",
        status="success",
    )
    _create_entry(
        repository,
        timestamp=now - timedelta(minutes=1),
        actor_type="user",
        actor_id="user-2",
        actor_email="user2@example.com",
        action="booking.cancel",
        resource_type="booking",
        resource_id="booking-2",
        status="failed",
    )

    entries, total, _summary = repository.search(
        actor_id="system",
        actor_types=["system"],
        action="payment.capture",
        resource_type="payment",
        resource_id="booking-1",
        since_hours=1,
        limit=5,
    )

    assert total == 1
    assert entries[0].id == target.id
