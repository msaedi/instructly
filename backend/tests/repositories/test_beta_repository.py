from datetime import datetime, timedelta, timezone


def test_beta_invite_repository_crud(db, test_student):
    from app.repositories.beta_repository import BetaInviteRepository

    repo = BetaInviteRepository(db)

    # Bulk create two invites
    now = datetime.now(timezone.utc)
    invites = repo.bulk_create_invites(
        [
            {
                "code": "TEST0001",
                "email": "a@example.com",
                "role": "instructor_beta",
                "expires_at": now + timedelta(days=7),
            },
            {"code": "TEST0002", "email": None, "role": "instructor_beta", "expires_at": now + timedelta(days=7)},
        ]
    )

    assert len(invites) == 2
    got = repo.get_by_code("TEST0001")
    assert got is not None
    assert got.email == "a@example.com"

    # mark_used returns True first time, False if repeated
    ok_first = repo.mark_used("TEST0001", user_id=test_student.id)
    ok_second = repo.mark_used("TEST0001", user_id=test_student.id)
    assert ok_first is True
    assert ok_second is False


def test_beta_access_repository_grant(db, test_student):
    from app.repositories.beta_repository import BetaAccessRepository, BetaInviteRepository

    # Ensure an invite exists for FK to invited_by_code
    invite_repo = BetaInviteRepository(db)
    now = datetime.now(timezone.utc)
    invite_repo.bulk_create_invites(
        [{"code": "TEST0001", "email": None, "role": "instructor_beta", "expires_at": now + timedelta(days=7)}]
    )

    repo = BetaAccessRepository(db)
    grant = repo.grant_access(
        user_id=test_student.id, role="instructor_beta", phase="instructor_only", invited_by_code="TEST0001"
    )
    assert grant is not None
    assert grant.user_id == test_student.id
    assert grant.role == "instructor_beta"
