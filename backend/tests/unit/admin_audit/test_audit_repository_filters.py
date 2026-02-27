from datetime import datetime, timedelta, timezone

import pytest

from app.models.audit_log import AuditLog
from app.repositories.audit_repository import AuditRepository


@pytest.fixture
def repository(db):
    return AuditRepository(db)


def _seed_logs(repo: AuditRepository) -> list[AuditLog]:
    base_time = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    entries: list[tuple[str, str, str, dict, dict, str, str]] = [
        ("booking", "bk-1", "create", {"status": "CONFIRMED"}, {"status": "CONFIRMED"}, "student-1", "student"),
        ("booking", "bk-1", "update", {"status": "CONFIRMED"}, {"status": "CONFIRMED", "instructor_note": "updated"}, "instr-1", "instructor"),
        ("booking", "bk-2", "cancel", {"status": "CONFIRMED"}, {"status": "CANCELLED"}, "admin-1", "admin"),
        ("availability", "instructor-1:2025-01-06", "save_week", {"window_counts": {}}, {"window_counts": {"2025-01-06": 2}}, "instr-1", "instructor"),
        ("booking", "bk-1", "cancel", {"status": "CONFIRMED"}, {"status": "CANCELLED"}, "student-1", "student"),
    ]

    created: list[AuditLog] = []
    for idx, (entity_type, entity_id, action, before, after, actor_id, actor_role) in enumerate(entries):
        log = AuditLog.from_change(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor={"id": actor_id, "role": actor_role},
            before=before,
            after=after,
        )
        log.occurred_at = base_time + timedelta(minutes=idx)
        repo.write(log)
        created.append(log)
    return created


def test_filters_and_sorting(repository: AuditRepository, db) -> None:
    _seed_logs(repository)

    items, total = repository.list(entity_type="booking", entity_id="bk-1", limit=10, offset=0)

    assert total == 3
    actions = [item.action for item in items]
    # Newest first (cancel, update, create)
    assert actions == ["cancel", "update", "create"]

    # Filter by actor role
    items, total = repository.list(actor_role="admin")
    assert total == 1
    assert items[0].actor_role == "admin"

    # Date range filter
    start = datetime(2025, 1, 1, 12, 1, tzinfo=timezone.utc)
    end = datetime(2025, 1, 1, 12, 2, tzinfo=timezone.utc)
    items, total = repository.list(start=start, end=end)
    assert total == 2
    assert {item.action for item in items} == {"update", "cancel"}

    # Pagination
    items, total = repository.list(entity_type="booking", limit=1, offset=1)
    assert total == 4
    assert len(items) == 1
    assert items[0].action == "cancel"
