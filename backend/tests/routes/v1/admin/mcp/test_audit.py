from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.models.audit_log import AuditLogEntry


def _create_entry(
    db,
    *,
    timestamp: datetime,
    actor_type: str,
    actor_id: str | None,
    actor_email: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None,
    status: str,
    metadata_json: dict | None = None,
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
        metadata_json=metadata_json,
        created_at=timestamp,
    )
    db.add(entry)
    db.flush()
    return entry


def test_audit_search_returns_summary(client: TestClient, db, mcp_service_headers) -> None:
    now = datetime.now(timezone.utc)
    _create_entry(
        db,
        timestamp=now - timedelta(minutes=10),
        actor_type="user",
        actor_id="user-1",
        actor_email="user1@example.com",
        action="booking.cancel",
        resource_type="booking",
        resource_id="booking-1",
        status="success",
    )
    _create_entry(
        db,
        timestamp=now - timedelta(minutes=5),
        actor_type="user",
        actor_id="user-2",
        actor_email="user2@example.com",
        action="user.update",
        resource_type="user",
        resource_id="user-2",
        status="failed",
    )
    db.commit()

    res = client.get(
        "/api/v1/admin/mcp/audit/search",
        params={"resource_type": "booking"},
        headers=mcp_service_headers,
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["meta"]["total_count"] == 1
    assert payload["summary"]["by_action"]["booking.cancel"] == 1
    assert payload["entries"][0]["resource"]["type"] == "booking"


def test_audit_user_activity_filters_by_email(
    client: TestClient, db, mcp_service_headers
) -> None:
    now = datetime.now(timezone.utc)
    _create_entry(
        db,
        timestamp=now - timedelta(minutes=5),
        actor_type="user",
        actor_id="user-1",
        actor_email="target@example.com",
        action="booking.create",
        resource_type="booking",
        resource_id="booking-1",
        status="success",
    )
    _create_entry(
        db,
        timestamp=now - timedelta(minutes=3),
        actor_type="user",
        actor_id="user-2",
        actor_email="other@example.com",
        action="booking.cancel",
        resource_type="booking",
        resource_id="booking-2",
        status="success",
    )
    db.commit()

    res = client.get(
        "/api/v1/admin/mcp/audit/users/target@example.com/activity",
        params={"since_days": 1},
        headers=mcp_service_headers,
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["meta"]["total_count"] == 1
    assert payload["entries"][0]["actor"]["email"] == "target@example.com"


def test_audit_resource_history_orders_newest_first(
    client: TestClient, db, mcp_service_headers
) -> None:
    now = datetime.now(timezone.utc)
    older = _create_entry(
        db,
        timestamp=now - timedelta(minutes=10),
        actor_type="user",
        actor_id="user-1",
        actor_email="user1@example.com",
        action="booking.create",
        resource_type="booking",
        resource_id="booking-1",
        status="success",
    )
    newer = _create_entry(
        db,
        timestamp=now - timedelta(minutes=1),
        actor_type="system",
        actor_id="system",
        actor_email=None,
        action="booking.complete",
        resource_type="booking",
        resource_id="booking-1",
        status="success",
    )
    db.commit()

    res = client.get(
        "/api/v1/admin/mcp/audit/resources/booking/booking-1/history",
        headers=mcp_service_headers,
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["entries"][0]["id"] == newer.id
    assert payload["entries"][1]["id"] == older.id


def test_audit_recent_admin_actions_filters_admins(
    client: TestClient, db, mcp_service_headers
) -> None:
    now = datetime.now(timezone.utc)
    _create_entry(
        db,
        timestamp=now - timedelta(minutes=15),
        actor_type="mcp",
        actor_id="svc-1",
        actor_email=None,
        action="mcp.invite_send",
        resource_type="mcp",
        resource_id="invite-1",
        status="success",
    )
    _create_entry(
        db,
        timestamp=now - timedelta(minutes=10),
        actor_type="user",
        actor_id="admin-1",
        actor_email="admin@example.com",
        action="user.update",
        resource_type="user",
        resource_id="user-3",
        status="success",
        metadata_json={"actor_roles": ["Admin"]},
    )
    _create_entry(
        db,
        timestamp=now - timedelta(minutes=5),
        actor_type="user",
        actor_id="student-1",
        actor_email="student@example.com",
        action="booking.create",
        resource_type="booking",
        resource_id="booking-3",
        status="success",
        metadata_json={"actor_roles": ["student"]},
    )
    db.commit()

    res = client.get(
        "/api/v1/admin/mcp/audit/admin-actions/recent",
        headers=mcp_service_headers,
    )
    assert res.status_code == 200
    payload = res.json()
    actions = {entry["action"] for entry in payload["entries"]}
    assert "mcp.invite_send" in actions
    assert "user.update" in actions
    assert "booking.create" not in actions
