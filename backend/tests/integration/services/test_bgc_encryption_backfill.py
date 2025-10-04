from __future__ import annotations

from cryptography.fernet import Fernet
from scripts import encrypt_bgc_report_ids

from app.core.config import settings
import app.core.crypto as crypto
from app.models.instructor import InstructorProfile
from app.models.user import User


def _set_encryption_key(value: str | None) -> None:
    settings.bgc_encryption_key = value
    crypto._FERNET_INSTANCE = None
    crypto._FERNET_KEY = None


def test_backfill_encrypts_plaintext_report_ids(db, monkeypatch):
    original_key = settings.bgc_encryption_key

    try:
        # Seed plaintext record with encryption disabled to simulate legacy data
        _set_encryption_key(None)
        monkeypatch.delenv("BGC_ENCRYPTION_KEY", raising=False)

        user = User(
            email="backfill@example.com",
            first_name="Backfill",
            last_name="Candidate",
            hashed_password="stub",
            zip_code="10001",
        )
        db.add(user)
        db.flush()

        profile = InstructorProfile(user_id=user.id)
        profile.bgc_report_id = "rpt_backfill"
        db.add(profile)
        db.flush()

        profile_id = profile.id
        assert getattr(profile, "_bgc_report_id") == "rpt_backfill"

        db.commit()

        # Enable encryption and run dry-run to verify no changes happen
        new_key = Fernet.generate_key().decode()
        _set_encryption_key(new_key)

        exit_code = encrypt_bgc_report_ids.main(["--limit", "10"])  # dry-run by default
        assert exit_code == 0

        db.expire_all()
        after_dry_run = db.get(InstructorProfile, profile_id)
        assert after_dry_run is not None
        assert getattr(after_dry_run, "_bgc_report_id") == "rpt_backfill"
        assert after_dry_run.bgc_report_id == "rpt_backfill"

        # Run commit mode to perform encryption in place
        exit_code = encrypt_bgc_report_ids.main(["--limit", "10", "--commit"])
        assert exit_code == 0

        db.expire_all()
        encrypted_profile = db.get(InstructorProfile, profile_id)
        assert encrypted_profile is not None
        encrypted_value = getattr(encrypted_profile, "_bgc_report_id")
        assert encrypted_value is not None
        assert encrypted_value != "rpt_backfill"
        assert encrypted_profile.bgc_report_id == "rpt_backfill"

        # Idempotency: running again should keep the same encrypted value
        exit_code = encrypt_bgc_report_ids.main(["--limit", "10", "--commit"])
        assert exit_code == 0

        db.expire_all()
        again_profile = db.get(InstructorProfile, profile_id)
        assert again_profile is not None
        assert getattr(again_profile, "_bgc_report_id") == encrypted_value
        assert again_profile.bgc_report_id == "rpt_backfill"
    finally:
        _set_encryption_key(original_key)
