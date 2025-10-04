from __future__ import annotations

from datetime import datetime, timezone

from cryptography.fernet import Fernet
import pytest

from app.core.config import settings
import app.core.crypto as crypto
from app.models.instructor import InstructorProfile
from app.models.user import User
from app.repositories.instructor_profile_repository import InstructorProfileRepository


@pytest.fixture
def bgc_encryption_key(monkeypatch: pytest.MonkeyPatch) -> str:
    key = Fernet.generate_key().decode()
    previous = settings.bgc_encryption_key

    settings.bgc_encryption_key = key
    crypto._FERNET_INSTANCE = None
    crypto._FERNET_KEY = None

    try:
        yield key
    finally:
        settings.bgc_encryption_key = previous
        crypto._FERNET_INSTANCE = None
        crypto._FERNET_KEY = None


def _create_user(db) -> User:
    user = User(
        email="encrypt-test@example.com",
        first_name="Encrypt",
        last_name="Tester",
        hashed_password="stub",
        zip_code="10001",
    )
    db.add(user)
    db.flush()
    return user


def test_bgc_report_id_encrypts_and_decrypts_transparently(db, bgc_encryption_key):
    user = _create_user(db)
    profile = InstructorProfile(user_id=user.id)
    db.add(profile)
    db.flush()

    plain_report = "rpt_plaintext"
    profile.bgc_report_id = plain_report
    db.flush()

    assert profile.bgc_report_id == plain_report
    stored = getattr(profile, "_bgc_report_id")
    assert stored is not None
    assert stored != plain_report

    db.expire_all()
    reloaded = db.get(InstructorProfile, profile.id)
    assert reloaded is not None
    assert reloaded.bgc_report_id == plain_report

    profile.bgc_report_id = None
    db.flush()
    assert profile.bgc_report_id is None

    profile.bgc_report_id = ""
    db.flush()
    assert profile.bgc_report_id == ""


def test_repository_lookup_by_report_id_handles_encrypted_values(db, bgc_encryption_key):
    user = _create_user(db)
    profile = InstructorProfile(user_id=user.id)
    db.add(profile)
    db.flush()

    report_id = "rpt_lookup"
    profile.bgc_report_id = report_id
    db.flush()

    repository = InstructorProfileRepository(db)

    updated = repository.update_bgc_by_report_id(
        report_id,
        status="passed",
        completed_at=datetime.now(timezone.utc),
    )
    assert updated == 1

    fetched = repository.get_by_report_id(report_id)
    assert fetched is not None
    assert fetched.id == profile.id
    assert fetched.bgc_report_id == report_id

    matches = repository.find_profile_ids_by_report_fragment("lookup")
    assert profile.id in matches
