from __future__ import annotations

from types import SimpleNamespace

from app.models import audit_log


def test_from_change_with_mapping_actor() -> None:
    actor = {"id": "actor-1", "role": "admin"}
    before = {"a": 1}
    after = {"b": 2}

    entry = audit_log.AuditLog.from_change(
        entity_type="booking",
        entity_id="b1",
        action="update",
        actor=actor,
        before=before,
        after=after,
    )

    assert entry.actor_id == "actor-1"
    assert entry.actor_role == "admin"
    assert entry.before == before
    assert entry.after == after


def test_from_change_with_object_actor_roles() -> None:
    actor = SimpleNamespace(id="actor-2", roles=["staff", "admin"])
    before = {"a": 1}
    after = {"b": 2}

    entry = audit_log.AuditLog.from_change(
        entity_type="user",
        entity_id="u1",
        action="delete",
        actor=actor,
        before=before,
        after=after,
    )

    assert entry.actor_id == "actor-2"
    assert entry.actor_role == "staff"


def test_from_change_copies_mutable_mappings() -> None:
    before = {"a": 1}
    after = {"b": 2}

    entry = audit_log.AuditLog.from_change(
        entity_type="user",
        entity_id="u1",
        action="update",
        actor=None,
        before=before,
        after=after,
    )

    assert entry.before is not before
    assert entry.after is not after


def test_first_attr_and_extract_value_helpers() -> None:
    obj = SimpleNamespace(user_id="u2")
    assert audit_log._first_attr(obj, ("missing", "user_id")) == "u2"

    data = {"actor_id": "u3"}
    assert audit_log._extract_value(data, ("id", "actor_id")) == "u3"
