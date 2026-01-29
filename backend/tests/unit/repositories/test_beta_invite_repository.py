from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.beta import BetaInvite
from app.repositories.beta_repository import BetaInviteRepository


def _create_invite(
    db,
    *,
    code: str,
    email: str,
    created_at: datetime,
    expires_at: datetime,
    used_at: datetime | None = None,
) -> BetaInvite:
    invite = BetaInvite(
        code=code,
        email=email,
        expires_at=expires_at,
    )
    invite.created_at = created_at
    if used_at:
        invite.used_at = used_at
    db.add(invite)
    db.flush()
    return invite


def test_list_invites_filters_status_email_and_dates(db):
    repo = BetaInviteRepository(db)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    accepted = _create_invite(
        db,
        code="ACC0001",
        email="accepted@example.com",
        created_at=now - timedelta(days=2),
        expires_at=now + timedelta(days=7),
        used_at=now - timedelta(days=1),
    )
    pending = _create_invite(
        db,
        code="PEND0001",
        email="pending@example.com",
        created_at=now - timedelta(days=1),
        expires_at=now + timedelta(days=7),
    )
    expired = _create_invite(
        db,
        code="EXP0001",
        email="expired@example.com",
        created_at=now - timedelta(days=3),
        expires_at=now - timedelta(days=1),
    )

    items, _ = repo.list_invites(status="accepted", now=now)
    assert {item.id for item in items} == {accepted.id}

    items, _ = repo.list_invites(status="pending", now=now)
    assert {item.id for item in items} == {pending.id}

    items, _ = repo.list_invites(status="expired", now=now)
    assert {item.id for item in items} == {expired.id}

    items, _ = repo.list_invites(status="revoked", now=now)
    assert items == []

    items, _ = repo.list_invites(email="pending@example.com", now=now)
    assert {item.id for item in items} == {pending.id}

    items, _ = repo.list_invites(
        start_date=(now - timedelta(days=2)).date(),
        end_date=(now - timedelta(days=1)).date(),
        now=now,
    )
    ids = {item.id for item in items}
    assert pending.id in ids
    assert accepted.id in ids


def test_list_invites_cursor_and_invalid_cursor(db):
    repo = BetaInviteRepository(db)
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)

    first = _create_invite(
        db,
        code="CUR0001",
        email="first@example.com",
        created_at=now - timedelta(days=0),
        expires_at=now + timedelta(days=7),
    )
    second = _create_invite(
        db,
        code="CUR0002",
        email="second@example.com",
        created_at=now - timedelta(days=1),
        expires_at=now + timedelta(days=7),
    )
    _create_invite(
        db,
        code="CUR0003",
        email="third@example.com",
        created_at=now - timedelta(days=2),
        expires_at=now + timedelta(days=7),
    )

    items, cursor = repo.list_invites(limit=2, now=now)
    assert cursor is not None
    assert {item.id for item in items} == {first.id, second.id}

    items, next_cursor = repo.list_invites(limit=2, cursor=cursor, now=now)
    assert len(items) == 1
    assert next_cursor is None

    with pytest.raises(ValueError):
        repo.list_invites(cursor="bad-cursor", now=now)
