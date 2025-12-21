

def test_beta_service_methods_execute(db):
    # Smoke test to ensure methods run with decorators present
    from app.services.beta_service import BetaService

    svc = BetaService(db)
    # validate_invite should return (False, 'not_found', None) for unknown code
    ok, reason, invite = svc.validate_invite("UNKNOWN1")
    assert ok is False
    assert reason in ("not_found", "expired", "used")

    # bulk_generate should create records
    created = svc.bulk_generate(count=1, role="instructor_beta", expires_in_days=7, source="test", emails=None)
    assert len(created) == 1

    # consume_and_grant should work when provided valid code and user
    code = created[0].code
    from app.models.user import User

    user = User(
        email="metrics@example.com",
        hashed_password="x",
        is_active=True,
        first_name="Met",
        last_name="Rics",
        zip_code="10001",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    grant, reason2, invite = svc.consume_and_grant(
        code=code, user_id=user.id, role="instructor_beta", phase="instructor_only"
    )
    assert grant is not None
    assert reason2 is None
    assert invite is not None
