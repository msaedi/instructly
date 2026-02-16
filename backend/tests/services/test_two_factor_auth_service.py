"""Service-level tests for TwoFactorAuthService TTL and setup validation."""
from datetime import datetime, timedelta, timezone

import pytest


def test_setup_verify_rejects_expired_setup(db, test_student):
    """Service rejects verification when setup is >15 minutes old."""
    from app.services.two_factor_auth_service import TwoFactorAuthService

    # Simulate setup initiated 20 minutes ago
    test_student.two_factor_setup_at = datetime.now(timezone.utc) - timedelta(minutes=20)
    test_student.totp_secret = "some_encrypted_value"
    test_student.totp_enabled = False
    db.flush()

    service = TwoFactorAuthService(db)
    with pytest.raises(ValueError, match="expired"):
        service.setup_verify(test_student, "123456")

    # Verify dangling secret was cleared
    db.refresh(test_student)
    assert test_student.totp_secret is None
    assert test_student.two_factor_setup_at is None


def test_setup_verify_rejects_without_initiation(db, test_student):
    """Service rejects verification when setup was never initiated."""
    from app.services.two_factor_auth_service import TwoFactorAuthService

    # Ensure no setup timestamp
    test_student.two_factor_setup_at = None
    test_student.totp_secret = None
    db.flush()

    service = TwoFactorAuthService(db)
    with pytest.raises(ValueError, match="not initiated"):
        service.setup_verify(test_student, "123456")
