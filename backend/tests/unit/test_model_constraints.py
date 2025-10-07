from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.instructor import InstructorProfile
from app.models.user import User


def _create_user(db) -> User:
    user = User(
        email="constraint-test@example.com",
        hashed_password="hashed",
        first_name="Constraint",
        last_name="Test",
        zip_code="10001",
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def test_live_requires_passed_bgc_constraint(db):
    """is_live can only be true when the BGC status is passed."""

    user = _create_user(db)
    profile = InstructorProfile(user_id=user.id, bgc_status="pending")
    db.add(profile)
    db.flush()

    profile.is_live = True

    with pytest.raises(IntegrityError):
        db.flush()

    db.rollback()

    profile.bgc_status = "passed"
    profile.is_live = True
    profile.bgc_completed_at = datetime.now(timezone.utc)

    db.flush()
