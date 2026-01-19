from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from app.repositories.user_repository import UserRepository


def test_basic_getters(db, test_student, test_instructor_with_availability):
    repo = UserRepository(db)

    assert repo.get_by_id(None) is None
    assert repo.get_by_id(test_student.id) is not None
    assert (
        repo.get_by_id(
            test_student.id,
            load_relationships=False,
            use_retry=False,
            short_timeout=True,
        )
        is not None
    )
    assert repo.get_by_email(test_student.email) is not None

    user = repo.get_with_roles_and_permissions(test_instructor_with_availability.id)
    assert user is not None
    assert user.roles

    user_roles = repo.get_with_roles(test_instructor_with_availability.id)
    assert user_roles is not None
    assert user_roles.roles


def test_role_helpers(db, test_student, test_instructor_with_availability):
    repo = UserRepository(db)

    assert repo.get_instructor(test_instructor_with_availability.id) is not None
    assert repo.get_instructor(test_student.id) is None
    assert repo.is_instructor(test_instructor_with_availability.id) is True
    assert repo.is_instructor(test_student.id) is False

    instructor_ids = repo.list_instructor_ids()
    assert test_instructor_with_availability.id in instructor_ids
    assert repo.get_by_email_with_roles_and_permissions(test_student.email) is not None


def test_counts_and_profile_versions(db, test_student):
    repo = UserRepository(db)
    assert repo.count_all() > 0
    assert repo.count_active() > 0

    test_student.profile_picture_version = 2
    db.commit()

    versions = repo.get_profile_picture_versions([test_student.id])
    assert versions[test_student.id] == 2
    assert repo.get_profile_picture_versions([]) == {}


def test_update_and_clear_profile(db, test_student):
    repo = UserRepository(db)

    updated = repo.update_profile(test_student.id, first_name="Updated")
    assert updated is not None
    assert updated.first_name == "Updated"

    test_student.profile_picture_key = "key"
    test_student.profile_picture_uploaded_at = datetime.now(timezone.utc)
    test_student.profile_picture_version = 3
    db.commit()

    assert repo.clear_profile_picture(test_student.id) is True

    repo.update_password(test_student.id, "hashed")
    db.refresh(test_student)
    assert test_student.hashed_password == "hashed"
    assert repo.update_profile("missing-user", first_name="Nope") is None
    assert repo.clear_profile_picture("missing-user") is False
    assert repo.update_password("missing-user", "hashed") is False


def test_bulk_queries(db, test_student, test_instructor_with_availability):
    repo = UserRepository(db)

    users = repo.get_by_ids([test_student.id, test_instructor_with_availability.id])
    assert len(users) >= 2

    active = repo.get_all_active()
    assert any(u.id == test_student.id for u in active)


def test_list_students_paginated(db, test_student):
    repo = UserRepository(db)

    students = repo.list_students_paginated(limit=10, offset=0)
    assert any(s.id == test_student.id for s in students)

    inactive_students = repo.list_students_paginated(
        limit=10, offset=0, only_active=False
    )
    assert any(s.id == test_student.id for s in inactive_students)

    empty = repo.list_students_paginated(limit=0, offset=0)
    assert empty == []

    future_students = repo.list_students_paginated(
        limit=10, since=datetime.now(timezone.utc) + timedelta(days=1)
    )
    assert future_students == []


def test_user_repository_error_paths():
    db = Mock()
    db.execute.side_effect = RuntimeError("boom")
    db.query.side_effect = RuntimeError("boom")
    repo = UserRepository(db)

    assert repo.get_by_id("missing", use_retry=False, short_timeout=True) is None
    assert repo.get_by_email("missing@example.com") is None
    assert repo.get_with_roles_and_permissions("missing") is None
    assert repo.get_by_email_with_roles_and_permissions("missing@example.com") is None
    assert repo.get_with_roles("missing") is None
    assert repo.get_instructor("missing") is None
    assert repo.list_instructor_ids() == []
    assert repo.count_all() == 0
    assert repo.count_active() == 0
    assert repo.get_profile_picture_versions(["missing"]) == {}
    assert repo.get_by_ids(["missing"]) == []
    assert repo.get_all_active() == []
    assert repo.list_students_paginated(limit=1) == []
