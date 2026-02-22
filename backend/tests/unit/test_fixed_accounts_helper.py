from __future__ import annotations

from backend.tests._utils.fixed_accounts import ensure_user
from sqlalchemy import func

from app.core.enums import RoleName
from app.models.user import User


def test_ensure_user_is_case_insensitive_and_idempotent(db):
    first = ensure_user(db, "Test.Instructor@Example.com", role="instructor")
    second = ensure_user(db, "test.instructor@example.com", role="instructor")

    assert first.id == second.id

    count = (
        db.query(User)
        .filter(func.lower(User.email) == "test.instructor@example.com")
        .count()
    )
    assert count == 1
    assert any(role.name == RoleName.INSTRUCTOR for role in second.roles)


def test_ensure_user_rejects_empty_email(db):
    try:
        ensure_user(db, "  ", role="student")
    except ValueError as exc:
        assert "email is required" in str(exc)
    else:  # pragma: no cover - defensive assertion path
        raise AssertionError("ensure_user should reject empty email")
