from datetime import datetime, timedelta, timezone

from app.core.ulid_helper import generate_ulid
from app.models.badge import BadgeDefinition, StudentBadge


def _ensure_badge_definition(db, slug: str = "test_badge", **kwargs) -> BadgeDefinition:
    badge = db.query(BadgeDefinition).filter(BadgeDefinition.slug == slug).first()
    if badge:
        return badge
    badge = BadgeDefinition(
        id=generate_ulid(),
        slug=slug,
        name=kwargs.get("name", slug.replace("_", " ").title()),
        description="Test badge",
        criteria_type=kwargs.get("criteria_type", "milestone"),
        criteria_config=kwargs.get("criteria_config", {}),
        display_order=kwargs.get("display_order", 1),
        is_active=True,
    )
    db.add(badge)
    db.flush()
    return badge


def _create_award(db, *, badge: BadgeDefinition, student_id: str, **kwargs) -> StudentBadge:
    award = StudentBadge(
        id=generate_ulid(),
        student_id=student_id,
        badge_id=badge.id,
        status=kwargs.get("status", "pending"),
        awarded_at=kwargs.get("awarded_at", datetime.now(timezone.utc)),
        hold_until=kwargs.get("hold_until"),
        confirmed_at=kwargs.get("confirmed_at"),
        revoked_at=kwargs.get("revoked_at"),
        progress_snapshot=kwargs.get("progress_snapshot"),
    )
    db.add(award)
    db.flush()
    return award


def test_admin_badges_requires_admin_auth(client, db, test_student, auth_headers):
    badge = _ensure_badge_definition(db, slug="admin_test_badge")
    _create_award(db, badge=badge, student_id=test_student.id)

    res = client.get("/api/admin/badges/pending", headers=auth_headers)
    assert res.status_code == 403


def test_admin_badges_list_pending_default(client, db, admin_user, auth_headers_admin, test_student):
    badge = _ensure_badge_definition(db, slug="admin_pending_badge")
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    _create_award(
        db,
        badge=badge,
        student_id=test_student.id,
        hold_until=now - timedelta(days=1),
        awarded_at=now - timedelta(days=2),
    )

    res = client.get("/api/admin/badges/pending", headers=auth_headers_admin)
    assert res.status_code == 200
    body = res.json()
    assert body["total"] >= 1
    assert any(item["badge"]["slug"] == "admin_pending_badge" for item in body["items"])


def test_admin_badges_status_filter_confirmed(client, db, admin_user, auth_headers_admin, test_student):
    badge = _ensure_badge_definition(db, slug="admin_confirmed_badge")
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    _create_award(
        db,
        badge=badge,
        student_id=test_student.id,
        status="confirmed",
        confirmed_at=now,
        awarded_at=now - timedelta(days=3),
    )

    res = client.get(
        "/api/admin/badges/pending",
        params={"status": "confirmed"},
        headers=auth_headers_admin,
    )
    assert res.status_code == 200
    body = res.json()
    assert any(item["badge"]["slug"] == "admin_confirmed_badge" for item in body["items"])


def test_admin_badges_confirm_endpoint(client, db, admin_user, auth_headers_admin, test_student):
    badge = _ensure_badge_definition(db, slug="admin_confirm_action")
    award = _create_award(db, badge=badge, student_id=test_student.id)

    res = client.post(f"/api/admin/badges/{award.id}/confirm", headers=auth_headers_admin)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "confirmed"

    # second confirm should return 404
    res = client.post(f"/api/admin/badges/{award.id}/confirm", headers=auth_headers_admin)
    assert res.status_code == 404


def test_admin_badges_revoke_endpoint(client, db, admin_user, auth_headers_admin, test_student):
    badge = _ensure_badge_definition(db, slug="admin_revoke_action")
    award = _create_award(db, badge=badge, student_id=test_student.id)

    res = client.post(f"/api/admin/badges/{award.id}/revoke", headers=auth_headers_admin)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "revoked"

    res = client.post(f"/api/admin/badges/{award.id}/revoke", headers=auth_headers_admin)
    assert res.status_code == 404


def test_admin_badges_confirm_nonexistent_returns_404(client, auth_headers_admin):
    res = client.post("/api/admin/badges/nonexistent/confirm", headers=auth_headers_admin)
    assert res.status_code == 404


def test_admin_badges_revoke_nonexistent_returns_404(client, auth_headers_admin):
    res = client.post("/api/admin/badges/nonexistent/revoke", headers=auth_headers_admin)
    assert res.status_code == 404
