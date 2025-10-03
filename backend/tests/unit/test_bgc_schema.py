from datetime import datetime, timezone

from app.auth import get_password_hash
from app.models import BGCConsent, InstructorProfile, User


def test_instructor_bgc_defaults_and_consent_relationship(db):
    user = User(
        email="bgc@example.com",
        hashed_password=get_password_hash("Test1234!"),
        first_name="BGC",
        last_name="Tester",
        zip_code="10001",
    )
    db.add(user)
    db.flush()

    instructor = InstructorProfile(user_id=user.id)
    db.add(instructor)
    db.flush()
    db.refresh(instructor)

    # New default: background checks start as "Not started" (NULL status) until consent/invite
    assert instructor.bgc_status is None
    assert instructor.bgc_env == "sandbox"
    assert instructor.bgc_report_id is None
    assert instructor.bgc_completed_at is None

    consent = BGCConsent(
        instructor_id=instructor.id,
        consent_version="v1",
        consented_at=datetime.now(timezone.utc),
    )
    db.add(consent)
    db.flush()
    db.refresh(consent)
    db.refresh(instructor)

    assert consent.instructor_profile.id == instructor.id
    assert instructor.bgc_consents[0].consent_version == "v1"
    assert instructor.bgc_consents[0].ip_address is None
