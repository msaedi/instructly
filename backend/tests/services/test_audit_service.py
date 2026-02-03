from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.core.request_context import reset_request_id, set_request_id
from app.models.audit_log import AuditLogEntry
from app.services.audit_redaction import REDACTED_VALUE
from app.services.audit_service import AuditService, audit_log


class DummyRequest:
    def __init__(self, headers: dict[str, str] | None = None, client_host: str | None = None):
        self.headers = headers or {}
        self.client = SimpleNamespace(host=client_host) if client_host else None


def test_log_creates_entry(db):
    service = AuditService(db)

    entry = service.log(
        action="booking.cancel",
        resource_type="booking",
        resource_id="01HXY1234567890ABCDEFGHJKL",
        actor_type="system",
    )

    stored = db.query(AuditLogEntry).filter(AuditLogEntry.id == entry.id).one()
    assert stored.action == "booking.cancel"
    assert stored.resource_type == "booking"
    assert stored.status == "success"


def test_log_with_actor(db):
    service = AuditService(db)
    actor = SimpleNamespace(id="user-123", email="user@example.com")

    entry = service.log(
        action="user.update",
        resource_type="user",
        resource_id="user-123",
        actor=actor,
    )

    stored = db.query(AuditLogEntry).filter(AuditLogEntry.id == entry.id).one()
    assert stored.actor_id == "user-123"
    assert stored.actor_email == "user@example.com"


def test_log_with_actor_mapping_resolves_fields(db):
    service = AuditService(db)
    actor = {"actor_id": "user-456", "user_email": "mapped@example.com"}

    entry = service.log(
        action="user.update",
        resource_type="user",
        resource_id="user-456",
        actor=actor,
    )

    stored = db.query(AuditLogEntry).filter(AuditLogEntry.id == entry.id).one()
    assert stored.actor_id == "user-456"
    assert stored.actor_email == "mapped@example.com"


def test_log_changes_detects_differences(db):
    service = AuditService(db)
    entry = service.log_changes(
        action="user.update",
        resource_type="user",
        resource_id="user-123",
        old_values={"first_name": "Alice", "last_name": "Smith"},
        new_values={"first_name": "Alicia", "last_name": "Smith"},
    )

    assert entry is not None
    stored = db.query(AuditLogEntry).filter(AuditLogEntry.id == entry.id).one()
    assert stored.changes == {"first_name": {"old": "Alice", "new": "Alicia"}}


def test_log_changes_no_changes_returns_none(db):
    service = AuditService(db)
    entry = service.log_changes(
        action="user.update",
        resource_type="user",
        resource_id="user-123",
        old_values={"first_name": "Alice"},
        new_values={"first_name": "Alice"},
    )
    assert entry is None


def test_get_client_ip_from_forwarded(db):
    service = AuditService(db)
    request = DummyRequest(
        headers={"x-forwarded-for": "203.0.113.4, 10.0.0.1", "user-agent": "TestAgent"},
        client_host="198.51.100.9",
    )

    entry = service.log(
        action="user.login",
        resource_type="user",
        resource_id="user-123",
        actor_type="user",
        actor_id="user-123",
        request=request,
    )

    stored = db.query(AuditLogEntry).filter(AuditLogEntry.id == entry.id).one()
    assert stored.actor_ip == "203.0.113.4"


def test_audit_includes_request_id(db):
    service = AuditService(db)
    token = set_request_id("req-123")
    try:
        entry = service.log(
            action="booking.create",
            resource_type="booking",
            resource_id="01HXY1234567890ABCDEFGHJKL",
            actor_type="system",
        )
    finally:
        reset_request_id(token)

    stored = db.query(AuditLogEntry).filter(AuditLogEntry.id == entry.id).one()
    assert stored.request_id == "req-123"


def test_log_redacts_sensitive_changes_and_metadata(db):
    service = AuditService(db)

    entry = service.log(
        action="user.update",
        resource_type="user",
        resource_id="user-123",
        changes={
            "password": {"old": "old-secret", "new": "new-secret"},
            "display_name": {"old": "Alice", "new": "Alicia"},
        },
        metadata={"access_token": "tok", "note": "safe"},
    )

    stored = db.query(AuditLogEntry).filter(AuditLogEntry.id == entry.id).one()
    assert stored.changes["password"]["old"] == REDACTED_VALUE
    assert stored.changes["password"]["new"] == REDACTED_VALUE
    assert stored.changes["display_name"]["new"] == "Alicia"
    assert stored.metadata_json["access_token"] == REDACTED_VALUE
    assert stored.metadata_json["note"] == "safe"


def test_log_adds_actor_roles_to_metadata(db):
    service = AuditService(db)
    actor = SimpleNamespace(
        id="user-123",
        email="user@example.com",
        role="admin",
        roles=[SimpleNamespace(name="support"), "admin"],
    )

    entry = service.log(
        action="user.update",
        resource_type="user",
        resource_id="user-123",
        actor=actor,
        metadata={"note": "updated"},
    )

    stored = db.query(AuditLogEntry).filter(AuditLogEntry.id == entry.id).one()
    assert stored.metadata_json["actor_roles"] == ["admin", "support"]
    assert stored.metadata_json["note"] == "updated"


def test_log_adds_actor_roles_from_mapping(db):
    service = AuditService(db)
    actor = {"role": "admin", "roles": ["support", "admin"]}

    entry = service.log(
        action="user.update",
        resource_type="user",
        resource_id="user-789",
        actor=actor,
        metadata={"note": "mapped"},
    )

    stored = db.query(AuditLogEntry).filter(AuditLogEntry.id == entry.id).one()
    assert stored.metadata_json["actor_roles"] == ["admin", "support"]
    assert stored.metadata_json["note"] == "mapped"


def test_log_preserves_explicit_actor_roles_metadata(db):
    service = AuditService(db)
    actor = SimpleNamespace(id="user-123", email="user@example.com", role="admin")

    entry = service.log(
        action="user.update",
        resource_type="user",
        resource_id="user-123",
        actor=actor,
        metadata={"actor_roles": ["custom"], "note": "override"},
    )

    stored = db.query(AuditLogEntry).filter(AuditLogEntry.id == entry.id).one()
    assert stored.metadata_json["actor_roles"] == ["custom"]
    assert stored.metadata_json["note"] == "override"


def test_log_user_agent_truncates(db):
    service = AuditService(db)
    user_agent = "a" * 600
    request = DummyRequest(headers={"user-agent": user_agent})

    entry = service.log(
        action="user.login",
        resource_type="user",
        resource_id="user-123",
        actor_type="user",
        actor_id="user-123",
        request=request,
    )

    stored = db.query(AuditLogEntry).filter(AuditLogEntry.id == entry.id).one()
    assert stored.actor_user_agent == user_agent[:500]


def test_log_client_ip_from_request_client(db):
    service = AuditService(db)
    request = DummyRequest(headers={"user-agent": "agent"}, client_host="198.51.100.9")

    entry = service.log(
        action="user.login",
        resource_type="user",
        resource_id="user-123",
        actor_type="user",
        actor_id="user-123",
        request=request,
    )

    stored = db.query(AuditLogEntry).filter(AuditLogEntry.id == entry.id).one()
    assert stored.actor_ip == "198.51.100.9"


def test_log_changes_normalizes_decimal_and_datetime(db):
    service = AuditService(db)
    entry = service.log_changes(
        action="payment.update",
        resource_type="payment",
        resource_id="pay-1",
        old_values={"amount": Decimal("10.00"), "captured_at": datetime(2025, 1, 1, tzinfo=timezone.utc)},
        new_values={"amount": Decimal("12.50"), "captured_at": datetime(2025, 1, 2, tzinfo=timezone.utc)},
    )

    assert entry is not None
    stored = db.query(AuditLogEntry).filter(AuditLogEntry.id == entry.id).one()
    assert stored.changes["amount"] == {"old": "10.00", "new": "12.50"}
    assert stored.changes["captured_at"]["new"] == "2025-01-02T00:00:00+00:00"


def test_audit_log_helper_creates_entry(db):
    entry = audit_log(
        db,
        action="booking.cancel",
        resource_type="booking",
        resource_id="01HXY1234567890ABCDEFGHJKL",
        actor_type="system",
    )

    stored = db.query(AuditLogEntry).filter(AuditLogEntry.id == entry.id).one()
    assert stored.action == "booking.cancel"
